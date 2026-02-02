# Nydus + Kata: 下一代容器镜像方案

您真的是太敏锐了！**Nydus** 确实是解开这种死结的“降维打击”武器。

这套方案不仅能复活 Firecracker，更是目前 Kata Containers 社区（尤其是蚂蚁集团、阿里云内部）生产环境的标准配置。

## 1. 为什么 Nydus 能救 Firecracker？

Firecracker 的死穴是：**“我不吃文件夹 (OverlayFS)，我只吃块设备 (Block Device)”。**

而 Nydus 的 **RAFTS** 格式镜像，恰好可以伪装成任何样子。

### 传统链路 (走不通)

> Docker Image (Layers) -> OverlayFS (Directory) -x-> Firecracker

### Nydus 链路 (走得通)

> Nydus Image (RAFTS) -> Nydus Snapshotter -> **Virtual Block Device (/dev/dm-x)** -> Firecracker

Nydus 可以在宿主机上把那个远程的镜像，瞬间呈现为一个**块设备**。Firecracker 以为这是一块本地硬盘，开心地挂载启动，实际上每次读写操作都被 Nydus 拦截，按需从远程 Registry 拉取数据。

### 1.1 架构澄清：千万别混搭

这里有一个常见的误区。**QEMU 和 Firecracker 是死对头（互斥关系），不能同时出现。**

您可以把它们理解为两款不同的“发动机”。Nydus 是“燃油”。

- **方案 A (推荐)**: **Kata + QEMU + Nydus**
  - **原理**: Nydus 作为一个 Filesystem Daemon 跑在宿主机。QEMU 通过 `virtio-fs` 协议，直接读取 Nydus 加载的数据。
  - **优点**: 兼容性 100%，支持文件夹结构，不需要把镜像转成块设备。
  - **速度**: 秒级启动。因为 QEMU 不需要等镜像下载完，Nydus 实现了 **Lazy Loading (按需加载)**——容器启动只需要 0.5秒，后面用到哪个文件再从网络下哪个文件。

- **方案 B (极客)**: **Kata + Firecracker + Nydus**
  - **原理**: Nydus 伪装成一个 Block Device。Firecracker 通过 `virtio-blk` 读取。
  - **缺点**: 工程复杂度极高，正如前文所述。

所以，咱们常说的“秒级启动”，通常是指 **方案 A**。

---

## 2. 架构代价与收益

要走通这条路，您需要对基础设施做一次**“大换血”**。

| 组件                 | 现状                   | Nydus 改造后                                    | 复杂度 |
| :------------------- | :--------------------- | :---------------------------------------------- | :----- |
| **构建 (Build)**     | `docker build`         | `nerdctl` + `nydusify convert` (必须由格式转换) | 🔴 高  |
| **存储 (Registry)**  | Harbor / DockerHub     | 必须支持 Nydus Backend (部分公有云还不支持)     | 🟡 中  |
| **节点 (Node)**      | Containerd + OverlayFS | Containerd + **Nydus Snapshotter**              | 🔴 高  |
| **运行时 (Runtime)** | Kata + QEMU            | Kata + QEMU + Nydus (Solution A)                | 🟢 优  |

## 3. 核心优势：为什么 Nydus 比我现在强的多？

这就好比 **“在线看视频” vs “下载完再看”** 的区别。

### 3.1 极速启动 (Cold Start)

- **现在的您 (OCI)**:
  - 如果您想跑一个 PyTorch 镜像 (3GB)。
  - 您必须等这 3GB **全部下载并解压完**，Agent 才能启动。耗时可能高达 **20-30秒**。
- **强在 Nydus**:
  - **Lazy Loading (按需加载)**。
  - 容器启动时，**完全不下载数据**，只下载几 KB 的元数据 (Metadata)。
  - Agent 可以在 **500ms 内** 启动。
  - 当代码运行 `import torch` 时，Nydus 才会去网络上拉取那一小段代码块。

### 3.2 带宽节省 (Bandwidth)

- **现在的您**: 即使您只用到了 pytorch 里 5% 的功能，您也必须下载 100% 的镜像。
- **强在 Nydus**: **只下载用到的数据**。业界统计表明，一般容器只会读取镜像中 6% 的数据。您的公网宽带费用能省 **90%**。

### 3.3 存储去重 (Deduplication)

- **现在的您**: 镜像去重粒度是 Layer (层)。如果两层只差一个文件，也得存两份。
- **强在 Nydus**: 去重粒度是 **Chunk (块)**。重复数据自动消除，节点磁盘利用率大幅提升。

#### 深度解析：Layer vs Chunk

这块如果不理解，可以想象成 **"下载一部 1GB 的电影"**。

1.  **OCI Layer (粗粒度)**:
    - Docker 就像是把这部电影打成了一个 `.tar.gz` 压缩包。
    - **痛点**: 如果您给电影加了 1 秒钟的片头（修改了数据），整个压缩包的哈希值就变了。K8s 认为这是一个全新的镜像，必须**重新下载这 1GB 的数据**。
    - **去重**: 只有两个镜像完全引用了同一个 Layer ID 时，才能共享空间。

2.  **Nydus Chunk (细粒度)**:
    - Nydus 会把这 1GB 的文件切成 2000 个小碎块（Chunk），每个 512KB。
    - **优势**: 如果您加了片头，可能只有前 5 个 Chunk 变了，后面 1995 个 Chunk 还是完全一样的。
    - **去重**: 这 1995 个 Chunk 在存储端和传输端都可以直接复用。这就是为什么 Nydus 更新镜像非常快。

## 4. 为什么蚂蚁最后没用 Firecracker？

这里有个非常有意思的技术八卦。

蚂蚁集团虽然开源了 Nydus，但他们内部并没有大量使用 "Nydus + Firecracker"。
因为 Firecracker 还是太“倔”了（功能缺失太多）。

蚂蚁最后这就为了配合 Nydus 的极致速度，自己造了一个 VMM 叫 **Dragonball**。

- **Dragonball** = Firecracker 的精简 + QEMU 的 virtio-fs 能力。
- 它是 Kata Containers 原生支持的第三种 Hypervisor。

## 4. 结论与建议

- **路径 A (折腾但能成)**: 您现在就可以在研发环境部署 Nydus Snapshotter，把 Python 镜像转成 Nydus 格式，然后强行配置 Firecracker 使用 Block Device Driver。这条路是通的。
- **路径 B (推荐)**: 继续用 QEMU + Nydus。
  - QEMU 配合 Nydus 的 `virtio-fs` 模式，其实已经做到了 **Seconds-level startup** (秒级启动)。
  - 您不仅拥有了极速启动，还保留了完整的 Linux 功能（不像 Firecracker 阉割了那么多）。

## 5. Nydus 落地改造指南 (Adoption Guide)

要引入 Nydus，您需要完成以下三个层面的改造：

### Step 1: 镜像转换 (Build Phase)

Nydus 镜像格式与普通 Docker 镜像不同，需要转换。

- **工具**: `nydusify` (官方转换工具)
- **命令**:
  ```bash
  # 把普通 python 镜像转换为 nydus 格式，并推送到 Registry
  ./nydusify convert \
    --source python:3.9 \
    --target my-registry.com/python:3.9-nydus \
    --backend-type registry \
    --backend-config '{"scheme":"http"}'
  ```

### Step 2: 节点改造 (Node Phase)

K8s 节点默认只会解压文件，不会挂载 Nydus 块。需要安装插件。

1.  **安装 Nydus Snapshotter**:
    下载并安装 `containerd-nydus-grpc` 守护进程。
2.  **配置 Containerd**:
    修改 `/etc/containerd/config.toml`，告诉它遇到 Nydus 镜像时，交给 Nydus 插件处理。
    ```toml
    [proxy_plugins.nydus]
      type = "snapshot"
      address = "/run/containerd-nydus/containerd-nydus-grpc.sock"
    ```

### Step 3: 运行时配置 (Runtime Phase)

对于 **Kata + QEMU**，这一步是最省心的——**零配置**。

- 只要 Step 2 配置好了，Nydus Snapshotter 会在宿主机上准备好目录。
- Kata (QEMU) 依然通过 `virtio-fs` 去挂载那个目录，它根本感觉不到底层数据是“偷懒加载”的。

---

**建议**: 先在一台测试节点上部署 `nydus-snapshotter`，手动跑通一个 Nydus 镜像，验证无误后再推行到生产集群。
