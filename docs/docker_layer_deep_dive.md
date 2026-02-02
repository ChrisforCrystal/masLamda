# Docker Layer 深度解析：洋葱的艺术

Docker 镜像本质上是一颗 **“洋葱”**。我们看到的完整文件系统，实际上是由无数层 **只读文件系统 (Read-Only Layers)** 叠加而成的错觉。

支撑这一切的核心技术叫做 **UnionFS (联合文件系统)**，目前主流的实现是 **OverlayFS**。

---

## 1. 层的诞生 (Anatomy of a Layer)

在 `Dockerfile` 中，只有以下三类指令会创建真正的“物理层”（占磁盘空间的层）：

1.  `RUN` (执行命令产生文件变化)
2.  `COPY` (复制文件)
3.  `ADD` (解压或下载文件)

_其他指令如 `ENV`, `CMD`, `EXPOSE` 只会修改镜像的元数据 (Metadata JSON)，大小为 0 Bytes。_

### 案例解剖

假设我们有这样一个 Dockerfile：

```dockerfile
# Layer 1: 基础镜像 (比如 100MB)
FROM python:3.9-slim

# Layer 2: 安装依赖包 (比如 200MB)
# 这一行产生了大量新文件
RUN pip install torch numpy

# Layer 3: 复制源代码 (比如 1MB)
COPY . /app

# (Metadata Only, 0MB)
CMD ["python", "app.py"]
```

### 最终结果：一张千层饼

当容器启动时，Docker 引擎会把这三层像奥利奥一样叠在一起。这里最容易晕，请记住**两个方向**：

#### 1. 构建方向 (Build Logic): 从下往上 ⬆️

这是 Dockerfile 执行的顺序，也是物理文件生成的顺序。

- **Layer 1 (底座)**: `FROM python`。最先生成，定死在地基上。
- **Layer 2 (中间)**: `RUN pip`。铺在 Layer 1 上面。
- **Layer 3 (上层)**: `COPY app`。铺在 Layer 2 上面。

#### 2. 查找方向 (Lookup Logic): 从上往下 ⬇️

这是程序读取文件时的视线方向。**谁在上面谁说了算**。

- **Layer 4 (Container Layer)**: [读写层] **(视线起点)**
  ⬇️ 穿透...
- **Layer 3**: 您的代码 `/app/main.py`
  ⬇️ 穿透...
- **Layer 2**: 依赖库 `/usr/local/lib/python3.9/site-packages/torch/...`
  ⬇️ 穿透...
- **Layer 1**: 操作系统 `/bin/bash`, `/usr/bin/python` **(视线终点)**

---

## 2. Copy-on-Write (写时复制) 的黑魔法

这是 Docker 节省空间的终极奥义。如果不理解，请想象一叠 **“透明胶片” (Transparencies)**。

我们在看这叠胶片时，是从**最上面**往下俯视的。

### 场景 A: 读取文件 (穿透视觉)

假设我们要找 `/usr/bin/python` 这个图案：

1.  **顶层 (Container Layer)**: 这一张是空的（透明的），什么也没画。于是视线**穿透**过去。
2.  **Layer 3**: 也是可以在这里画画的，但这里没画 Python，只画了 `app.py`。视线继续穿透。
3.  **Layer 2**: 这里画了 `torch`，但没画 Python。视线继续穿透。
4.  **Layer 1**: **终于！** 在这张纸上画着 `python` 的图案。
5.  **结果**: 您的眼睛（应用程序）看到了 Layer 1 里的 Python。

> **感官错觉**: 对您来说，您不知道（也不在乎）这个 Python 到底是在哪一层。您只看到“眼前有一个 Python”。这就是 UnionFS 的合并视图。

### 场景 B: 修改文件 (覆盖)

当您想修改 `/app/config.py` (位于 Layer 3) 时：

1.  Docker 发现 Layer 3 是只读的，不能改。
2.  **Copy**: 它会把 `config.py` 从 Layer 3 **复制** 到最上方的 **Container Layer**。
3.  **Write**: 您的程序修改的是 Container Layer 里那个副本。
4.  **遮挡**: 原本 Layer 3 里的那个文件依然存在，但对您不可见了（被顶层副本遮挡了）。

### 场景 C: 再次修改文件 (就地更新)

如果您紧接着又改了一次 `config.py`，会发生什么？

1.  Docker 发现 **顶层 (Container Layer)** 里已经有 `config.py` 的副本了。
2.  **直接修改**: 这次不需要再从下面复制了，直接修改顶层这一个文件。
3.  **结论**: 顶层是一个**标准的可读写文件系统**。无论您改多少次 A，都只是在改顶层的那同一个文件 A。不会产生“顶层之上的顶层”。

---

## 3. 最佳实践：如何利用分层做缓存？

K8s 拉取镜像的逻辑是：**只要这一层的 SHA256 Hash 没变，我就不下载，直接用本地缓存。**

所以，写 Dockerfile 的黄金法则只有一条：**“越不常变的东西，越往下面放”**。

### ❌ 错误写法 (缓存失效灾难)

```dockerfile
COPY . /app              # <--- 1. 先复制源代码 (代码每天都在变!)
RUN pip install torch    # <--- 2. 再装依赖 (500MB)
```

**后果**：因为第 1 层变了，Docker 认为第 2 层的环境可能受第 1 层影响，所以**第 2 层缓存作废**。每次改一行代码，都要重新下载 500MB 的 PyTorch。

### ✅ 正确写法 (完美缓存)

```dockerfile
COPY requirements.txt .  # <--- 1. 先只复制依赖描述文件 (不常变)
RUN pip install -r requirements.txt # <--- 2. 装依赖 (500MB - 这一层会被永久缓存!)
COPY . /app              # <--- 3. 最后才复制频繁变动的代码 (1MB)
```

**后果**：无论怎么改代码，只要 `requirements.txt` 没变，前两层永远是从缓存读，构建和发布速度极快。

---

## 4. 为什么要有 "RUN ... && ... && ..." ?

您经常看到这样的写法：

```dockerfile
RUN apt-get update && \
    apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*  # <--- 清理垃圾
```

为什么要写成一行？
因为**每一层都是独立的**。

如果您写成三行：

1.  `RUN apt-get update` (Layer A: 下载了 50MB 缓存)
2.  `RUN apt-get install git` (Layer B: 装软件)
3.  `RUN rm -rf ...` (Layer C: 删文件)

**结果**：用户下载镜像时，依然下载了 Layer A 里的 50MB 垃圾数据！虽然 Layer C 把它标记为“已删除”，但它物理上依然存在于 Layer A 的压缩包里。
**只有在同一层里创建并删除**，垃圾数据才不会被带入最终镜像。

---

## 5. 顶层的宿命：它是“一次性”的 (The Ephemeral Layer)

您问得很好，顶层确实可以被不断修改，但它有一个致命的弱点：**随生随死**。这里的“死”是指**容器被删除的那一刻**。

### 生命周期图解 (Timeline)

1.  **09:00 (Run)**: `docker run` 启动容器。
    - --> Docker 创建了全新的顶层 (Layer ID: abc)。
2.  **09:01 (Modify)**: 您修改了 A。
    - --> A 被复制到 Layer abc 中并被修改。您还能在容器里**看见**修改后的 A。
3.  **09:02 (Modify Again)**: 您又修改了 A。
    - --> Layer abc 里的 A 再次被更新。您还能**看见**最新版的 A。
4.  **09:05 (Stop)**: `docker stop` 停止容器。
    - --> Layer abc 依然存在在磁盘上，只是不再活跃。如果您 `docker start` 回来，数据还在。
5.  **09:10 (Remove)**: `docker rm` 删除容器。
    - --> **重点！** Docker 删除了 Layer abc 对应的文件夹。
    - --> **后果**：您修改的那个 A 彻底消失了。

### 突围方案：Volume (挂载卷)

如果您想保存数据（比如数据库文件），绝对不能写在顶层。您需要用 **Volume**。

Volume 就像是在所有的胶片上**打了一个洞**。

- 当您往这个洞里写数据时，数据直接落到了**宿主机的硬盘上**，完全绕过了 OverlayFS 的层级机制。
- 这就解释了为什么我们在 `agent_sandbox_policy.yaml` 里配了 `emptyDir` —— 我们是在胶片上打了个洞，让 Agent 的临时文件直接落盘，既快又安全（因为不会把顶层胶片撑爆）。
