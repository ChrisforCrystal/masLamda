# 在 VMware 上构建 Kata Containers 集群指南

Master, 关于您的问题：**"我现有的 VMware K8S 集群能直接跑 Kata 吗？"**

**答案是：取决于您当初创建虚拟机时，有没有勾选那个关键的 "开启虚拟化" 选项。**

绝大多数默认创建的 VMware 虚拟机是**没有**开启这个选项的。这意味着直接跑 Kata 会失败（因为它依赖 KVM）。

---

## 1. 快速体检（无需猜测）

我为您写了一个检测脚本。请把这个脚本复制到您的 **K8S Worker Node** 上执行：

```bash
# 复制 check_kata_readiness.sh 到节点上并运行
chmod +x check_kata_readiness.sh
./check_kata_readiness.sh
```

- 如果输出 **✅ CPU supports Virtualization** -> **恭喜！您可以直接安装 Kata。**
- 如果输出 **❌ CPU does NOT support Virtualization** -> **很遗憾，您需要停机调整。**

---

## 2. 如果检测不通过，如何调整？

您不需要重建集群，但需要**重启节点**：

1.  **驱逐节点 (可选)**: `kubectl drain <node-name>` (如果业务不能中断)。
2.  **关机**: 在 VMware 控制台关闭该虚拟机。
3.  **修改设置**:
    - 右键虚拟机 -> **Edit Settings**。
    - **CPU** -> 勾选 ✅ **Expose hardware assisted virtualization to the guest OS**。
4.  **开机**: 启动虚拟机。
5.  **恢复**: 再次运行检测脚本，确认变绿。

只要您的 CPU 支持虚拟化，Kata 就能跑。网络方面（Flannel/Calico）通常不需要动。

---

## 3. 安装步骤 (Operator)

最简单的办法是使用 **Kata-deploy Operator** (和我们之前用的 KWasm 类似)。

```bash
# 1. 安装 Operator
kubectl apply -f https://raw.githubusercontent.com/kata-containers/kata-containers/main/tools/packaging/kata-deploy/kata-rbac/base/kata-rbac.yaml
kubectl apply -f https://raw.githubusercontent.com/kata-containers/kata-containers/main/tools/packaging/kata-deploy/kata-deploy/base/kata-deploy.yaml

# 2. 创建 RuntimeClass
kubectl apply -f https://raw.githubusercontent.com/kata-containers/kata-containers/main/tools/packaging/kata-deploy/runtimeclasses/kata-runtimeClasses.yaml
```

**使用方法**:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kata-test
spec:
  runtimeClassName: kata-qemu # <--- 指定使用 Kata
  containers:
    - name: nginx
      image: nginx
```

## 4. 常见坑 (Pitfalls)

1.  **性能损耗**: "套娃" (Nested Virtualization) 会带来显著的性能下降（网络和 IO）。作为开发/测试环境完全没问题，但生产环境建议直接在物理机 (Bare Metal) 上跑 Kata，或者使用支持裸金属实例的云主机（如 AWS i3.metal）。
2.  **网络插件 (CNI)**: Kata 对 CNI 插件比较挑剔。确保您的 K8S 使用的是标准的 Flannel 或 Calico。VXLAN 模式通常比 BGP 模式更容易配置。
