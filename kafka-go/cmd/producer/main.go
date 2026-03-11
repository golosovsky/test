// Producer: reads lines from stdin and publishes each as a Kafka message.
// Usage: go run ./cmd/producer
package main

import (
	"bufio"
	"context"
	"fmt"
	"log"
	"os"

	kafkalib "github.com/segmentio/kafka-go"
	"kafka-go/pkg/kafka"
)

func main() {
	writer := kafka.NewWriter()
	defer writer.Close()

	fmt.Println("Type messages (one per line). Ctrl+C to quit.")

	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		text := scanner.Text()
		if err := publish(writer, text); err != nil {
			log.Printf("publish failed: %v", err)
			continue
		}
		fmt.Printf("sent: %s\n", text)
	}
}

// publish sends a single message to Kafka.
func publish(writer *kafkalib.Writer, value string) error {
	return writer.WriteMessages(context.Background(),
		kafkalib.Message{Value: []byte(value)},
	)
}
