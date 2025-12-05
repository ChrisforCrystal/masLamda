package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"time"

	pb "flash-controller/pb"

	"github.com/gin-gonic/gin"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	// 1. 连接到 Flash Runner (Rust 服务)
	// 使用 gRPC 协议连接本地的 50051 端口
	conn, err := grpc.Dial("127.0.0.1:50051",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultCallOptions(grpc.MaxCallRecvMsgSize(50*1024*1024), grpc.MaxCallSendMsgSize(50*1024*1024)),
	)
	if err != nil {
		log.Fatalf("did not connect: %v", err)
	}
	defer conn.Close()
	client := pb.NewRunnerServiceClient(conn)

	// 2. 初始化 Gin Web 框架
	r := gin.Default()

	// 静态文件服务：提供 Dashboard 页面
	// 注意：这里假设运行目录是 flash-controller，而 dashboard 在上一级目录
	r.Static("/dashboard", "../flash-dashboard")
	r.GET("/", func(c *gin.Context) {
		c.Redirect(http.StatusMovedPermanently, "/dashboard")
	})

	// 状态检查 API
	r.GET("/status", func(ctx *gin.Context) {
		// 返回集群节点状态 (目前是 Mock 数据)
		ctx.JSON(http.StatusOK, gin.H{
			"nodes": []gin.H{
				{
					"address":        "127.0.0.1:50051",
					"status":         "Healthy",
					"last_heartbeat": time.Now().Format(time.RFC3339),
				},
			},
		})
	})

	// 核心运行 API: POST /run
	// Run API
	r.POST("/run", func(c *gin.Context) {
		// Read Wasm binary from request body
		wasmBytes, err := ioutil.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to read request body"})
			return
		}

		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		resp, err := client.Execute(ctx, &pb.ExecuteRequest{
			WasmBinary: wasmBytes,
			InputData:  []byte{},
		})

		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		log.Printf("Received response: output_len=%d, error=%s", len(resp.OutputData), resp.Error)

		c.JSON(http.StatusOK, gin.H{
			"output":         string(resp.OutputData),
			"error":          resp.Error,
			"execution_time": fmt.Sprintf("%d ns", resp.ExecutionTimeNs),
		})
	})

	// 新增: Service Mode API (支持输入参数)
	// 使用 Multipart Form Data:
	// - file: Wasm 文件
	// - input: 输入字符串 (JSON 或 文本)
	r.POST("/run_with_input", func(c *gin.Context) {
		log.Println("Received /run_with_input request")
		// 1. 解析 Multipart Form
		file, err := c.FormFile("file")
		if err != nil {
			log.Printf("Error getting form file: %v", err)
			c.JSON(http.StatusBadRequest, gin.H{"error": "Missing 'file' field"})
			return
		}
		log.Printf("Got file: %s, size: %d", file.Filename, file.Size)

		// 读取 Wasm 文件内容
		f, err := file.Open()
		if err != nil {
			log.Printf("Error opening file: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to open file"})
			return
		}
		defer f.Close()
		wasmBytes, err := ioutil.ReadAll(f)
		if err != nil {
			log.Printf("Error reading file: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to read file"})
			return
		}
		log.Printf("Read %d bytes from file", len(wasmBytes))

		// 2. 获取 input 参数
		inputData := c.PostForm("input")
		log.Printf("Got input data: %s", inputData)

		// 3. 调用 Runner (FaaS)
		log.Println("Calling gRPC Execute...")
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		resp, err := client.Execute(ctx, &pb.ExecuteRequest{
			WasmBinary: wasmBytes,
			InputData:  []byte(inputData), // 将输入传给 Runner
		})

		if err != nil {
			log.Printf("gRPC Execute failed: %v", err)
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		log.Println("gRPC Execute success")

		c.JSON(http.StatusOK, gin.H{
			"output":         string(resp.OutputData),
			"error":          resp.Error,
			"execution_time": fmt.Sprintf("%d ns", resp.ExecutionTimeNs),
		})
	})

	// Service Mode APIs
	// 1. Deploy Service (部署服务)
	// 流程:
	// 1. 客户端上传 Wasm 文件
	// 2. Controller 读取文件内容
	// 3. Controller 通过 gRPC 调用 Runner 的 DeployService 接口
	// 4. Runner 保存文件并启动服务，返回 Service ID
	r.POST("/deploy", func(c *gin.Context) {
		file, err := c.FormFile("file")
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Missing 'file' field"})
			return
		}
		f, err := file.Open()
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to open file"})
			return
		}
		defer f.Close()
		wasmBytes, err := ioutil.ReadAll(f)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to read file"})
			return
		}

		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		// gRPC 调用: 部署服务
		resp, err := client.DeployService(ctx, &pb.DeployRequest{
			WasmBinary: wasmBytes,
		})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"service_id": resp.ServiceId, "error": resp.Error})
	})

	// 2. Stop Service (停止服务)
	r.POST("/services/:id/stop", func(c *gin.Context) {
		id := c.Param("id")
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		resp, err := client.StopService(ctx, &pb.StopRequest{ServiceId: id})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"success": resp.Success, "error": resp.Error})
	})

	// 3. List Services (列出所有服务)
	r.GET("/services", func(c *gin.Context) {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		resp, err := client.ListServices(ctx, &pb.ListRequest{})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"services": resp.Services})
	})

	// 4. Get Service Logs (获取服务日志)
	r.GET("/services/:id/logs", func(c *gin.Context) {
		id := c.Param("id")
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		resp, err := client.GetLogs(ctx, &pb.GetLogsRequest{ServiceId: id})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"logs": resp.Logs, "error": resp.Error})
	})

	// 5. Invoke Service Method (调用服务方法)
	// 流程:
	// 1. 客户端发送 JSON 请求 (包含 method 和 params)
	// 2. Controller 解析请求
	// 3. Controller 通过 gRPC 调用 Runner 的 InvokeService 接口
	// 4. Runner 将请求转发给 Wasm 服务，并等待响应
	// 5. Runner 返回结果给 Controller，Controller 返回给客户端
	r.POST("/services/:id/invoke", func(c *gin.Context) {
		id := c.Param("id")

		var req struct {
			Method string      `json:"method"`
			Params interface{} `json:"params"`
		}
		if err := c.BindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid JSON body"})
			return
		}

		paramsBytes, err := json.Marshal(req.Params)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to marshal params"})
			return
		}

		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		// gRPC 调用: 调用服务
		resp, err := client.InvokeService(ctx, &pb.InvokeRequest{
			ServiceId: id,
			Method:    req.Method,
			Params:    string(paramsBytes),
		})

		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		if resp.Error != "" {
			c.JSON(http.StatusInternalServerError, gin.H{"error": resp.Error})
			return
		}

		// Result is a JSON string, we should parse it to return as JSON object
		var resultObj interface{}
		if err := json.Unmarshal([]byte(resp.Result), &resultObj); err != nil {
			// If not valid JSON, return as string
			c.JSON(http.StatusOK, gin.H{"result": resp.Result})
		} else {
			c.JSON(http.StatusOK, gin.H{"result": resultObj})
		}
	})

	r.Run(":8999") // 启动 HTTP 服务，监听 8999 端口
}
