package main

import (
	"bytes"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
)

func main() {
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	// Add file
	file, err := os.Open("echo.wat")
	if err != nil {
		fmt.Println("Error opening file:", err)
		return
	}
	defer file.Close()

	part, err := writer.CreateFormFile("file", "echo.wat")
	if err != nil {
		fmt.Println("Error creating form file:", err)
		return
	}
	io.Copy(part, file)

	// Add input field
	writer.WriteField("input", "Hello Wasm Service!")

	writer.Close()

	req, err := http.NewRequest("POST", "http://127.0.0.1:8999/run_with_input", body)
	if err != nil {
		fmt.Println("Error creating request:", err)
		return
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	client := &http.Client{}
	fmt.Println("Sending request...")
	resp, err := client.Do(req)
	if err != nil {
		fmt.Println("Error sending request:", err)
		return
	}
	defer resp.Body.Close()

	fmt.Println("Response Status:", resp.Status)
	b, _ := io.ReadAll(resp.Body)
	fmt.Println("Response Body:", string(b))
}
