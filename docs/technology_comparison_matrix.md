# AI Sandbox 技术横向评测 (The Ultimate Battle)

Master，为了帮您做最终的技术选型决策，我将目前市面上最主流的 5 种沙箱技术做了全方位对比。

---

## 1. 核心对比矩阵 (The Matrix)

| 特性         | **Standard (Docker)**  | **gVisor (Google)** | **Kata Containers**  | **Firecracker (AWS)**    | **WASM (WasmEdge)**              |
| :----------- | :--------------------- | :------------------ | :------------------- | :----------------------- | :------------------------------- |
| **隔离原理** | 进程级 (Namespace)     | 进程级 + 用户态内核 | 虚拟机 (MicroVM)     | 虚拟机 (MicroVM)         | 内存级 (SFI)                     |
| **内核**     | 共享宿主内核 ❌        | 模拟内核 (Sentry)   | 独立 Guest Kernel ✅ | 独立 Guest Kernel ✅     | 无 (Host调用)                    |
| **启动速度** | ⚡️ 极快 (<100ms)       | 🚀 快 (200ms)       | 🐢 较慢 (500ms+)     | 🐇 极快 (125ms)          | ⚡️⚡️ 瞬时 (0-5ms)                |
| **内存开销** | 极低                   | 低                  | 高 (QEMU 需 ~100MB)  | 极低 (~5MB)              | 极低                             |
| **兼容性**   | ⭐️⭐️⭐️⭐️⭐️ 完美        | ⭐️⭐️⭐️⭐️ 优         | ⭐️⭐️⭐️⭐️⭐️ 完美      | ⭐️⭐️⭐️⭐️ 优              | ⭐️⭐️ 差 (仅支持编译为Wasm的语言) |
| **安全性**   | ⚠️ 低 (防不住内核逃逸) | 🛡️ 高 (攻击面小)    | 🧱 极高 (硬件隔离)   | 🧱 极高 (硬件隔离)       | 🔒 高 (内存隔离)                 |
| **生态对接** | K8S 原生               | K8S (RuntimeClass)  | K8S (RuntimeClass)   | 需自行编排 (或通过 Kata) | K8S (KWasm)                      |

---

## 2. 详细优缺点点评 (Pros & Cons)

### 1. Standard Containers (RunC)

- 👍 **优点**: 大家都熟，生态最完善，性能几乎无损耗。
- 👎 **缺点**: **不仅不安全，是非常不安全**。只要有一个 Kernel Exploit，整台机器沦陷。绝对不能用来跑不可信的 AI 代码。

### 2. gVisor (Google 实现)

- 👍 **优点**: 平衡点找得最好。既有容器的使用体验，又有接近 VM 的安全性。Google Colab/Cloud Run 都在用。
- 👎 **缺点**: 系统调用 (Syscall) 是模拟的，稍微慢一点点，且极少数生僻的 Syscall 可能不支持。

### 3. Kata Containers

- 👍 **优点**: **最标准的 "在 K8S 里跑虚拟机" 的方案**。兼容性无敌，因为它就是个真 Linux VM。OpenStack 基金会背书。
- 👎 **缺点**: **重**。如果你要跑 1000 个沙箱，Kata (基于 QEMU) 可能会把你的内存吃光。嵌套虚拟化配置麻烦。

### 4. Firecracker (AWS 实现)

- 👍 **优点**: 做的比 Kata 更极致。专门为 Serverless 优化，启动快、内存省。
- 👎 **缺点**: **存储模型不兼容 (Blocker)**。
  - **不支持 virtio-fs**: 这一点这直接击穿了 Kata 的文件共享模型。Firecracker 仅支持 `virtio-block` / `virtio-mmio`。
  - **后果**: 必须将容器镜像转换成 ext4 块设备镜像才能挂载，无法直接复用宿主机的 OverlayFS 文件，导致出现 `failed to mount rootfs` 致命错误。
  - **很难直接对接 K8S**: 通常作为 Kata 的后端插件来使用 (Kata + Firecracker)，而不是直接用。

### 5. WASM (WasmEdge)

- 👍 **优点**: **降维打击**。启动速度快到忽略不计。非常适合它是 "函数级" 沙箱 (Serverless Functions)。
- 👎 **缺点**: **不是 Linux**。你不能跑 `apt-get`，不能跑 `pip install numpy` (除非预编译好)。它适合跑纯逻辑，不适合跑通用环境。

---

## 3. 选型建议 (The Verdict)

- **如果您要跑通用的 Python 代码 (带 Numpy/Pandas)**:
  - **首选**: **gVisor** (部署简单，兼容性好)。
  - **进阶**: **Kata + Firecracker** (如果对安全性有极高洁癖)。

- **如果您要跑 AI 推理逻辑 / 简单胶水代码**:
  - **首选**: **WASM** (快，省资源，安全)。

- **我们的架构 (Unified Trinity)**:
  - 正是结合了这两者的优点：用 **WASM** 处理高频轻量任务，用 **Standard/gVisor** 处理重型兼容任务。
