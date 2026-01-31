#!/bin/bash
set -e

echo "🚀 [Step 1] Creating Kata RBAC & ServiceAccount (Inline)..."
# 手动创建 RBAC，赋予读取 Node 信息的权限
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: kata-label-node
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kata-label-node
rules:
- apiGroups: [""]
  resources: ["nodes", "pods", "configmaps", "serviceaccounts", "services"]
  verbs: ["get", "list", "watch", "update", "patch", "create", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "daemonsets"]
  verbs: ["get", "list", "watch", "update", "patch", "create", "delete"]
- apiGroups: ["apiextensions.k8s.io"]
  resources: ["customresourcedefinitions"]
  verbs: ["get", "list", "watch", "create", "update", "patch"]
- apiGroups: ["nfd.k8s-sigs.io"]
  resources: ["nodefeaturerules"]
  verbs: ["get", "list", "watch", "create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kata-label-node
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kata-label-node
subjects:
- kind: ServiceAccount
  name: kata-label-node
  namespace: kube-system
EOF

echo "🚀 [Step 2] Deploying Kata DaemonSet (Using Private Registry)..."
# 我们直接在这里生成 YAML，替换掉官方镜像地址
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: kata-deploy
  namespace: kube-system
  labels:
    app: kata-deploy
spec:
  selector:
    matchLabels:
      name: kata-deploy
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
  template:
    metadata:
      labels:
        name: kata-deploy
    spec:
      # 使用我们刚创建的有权限的 ServiceAccount
      serviceAccountName: kata-label-node
      hostNetwork: true
      containers:
        - name: kube-kata
          # [关键修改] 使用您的内网镜像 3.9.0 版本（验证过包含完整文件）
          image: image.midea.com/midea-middleware/kata-deploy:3.9.0
          imagePullPolicy: Always
          lifecycle:
            preStop:
              exec:
                # 直接调用二进制 cleanup
                command: ["/usr/bin/kata-deploy", "cleanup"]
          # Use default Entrypoint, explicitly call kata-deploy binary
          command: ["/usr/bin/kata-deploy"]
          args: [ "install" ]
          env:
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
          securityContext:
            privileged: true
          volumeMounts:
            - name: cgroup
              mountPath: /sys/fs/cgroup
            - name: dbus
              mountPath: /var/run/dbus
            - name: systemd
              mountPath: /run/systemd
            - name: local-bin
              mountPath: /usr/local/bin/
            - name: kata-artifacts
              mountPath: /opt/kata/
            - name: container-runtime
              mountPath: /run/containerd/io.containerd.runtime.v2.task/
              
            # 适配不同的 Containerd 配置文件路径 (Standard paths)
            - name: containerd-conf
              mountPath: /etc/containerd/
            - name: containerd-conf-2
              mountPath: /var/run/containerd/
      volumes:
        - name: cgroup
          hostPath:
            path: /sys/fs/cgroup
        - name: dbus
          hostPath:
            path: /var/run/dbus
        - name: systemd
          hostPath:
            path: /run/systemd
        - name: local-bin
          hostPath:
            path: /usr/local/bin/
        - name: kata-artifacts
          hostPath:
            path: /opt/kata/
        - name: container-runtime
          hostPath:
            path: /run/containerd/io.containerd.runtime.v2.task/
        - name: containerd-conf
          hostPath:
            path: /etc/containerd/
        - name: containerd-conf-2
          hostPath:
            path: /var/run/containerd/
EOF

echo "🚀 [Step 3] Registering 'kata-fc' (Firecracker) RuntimeClass..."
# 这是告诉 K8s 如何使用 Firecracker 的关键配置
cat <<EOF | kubectl apply -f -
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata-fc
handler: kata-fc
overhead:
  podFixed:
    memory: "120Mi"
    cpu: "250m"
# [Modify] Removed scheduling constraint since we want to force run it anywhere
# scheduling:
#   nodeSelector:
#     katacontainers.io/kata-runtime: "true"
EOF

echo "✨ Deployment Submitted! Waiting for Pods to be ready..."
kubectl wait --for=condition=Ready pod -l name=kata-deploy -n kube-system --timeout=120s
echo "✅ Kata Containers (with Firecracker) Installed Successfully!"
