// Consumer: reads messages from Kafka and prints them.
// Usage: go run ./cmd/consumer
package main

import (
	"context"
	"fmt"
	"log"

	kafkalib "github.com/segmentio/kafka-go"
	"kafka-go/pkg/kafka"
)

func main() {
	reader := kafka.NewReader()
	defer reader.Close()

	fmt.Println("Listening for messages...")

	// Block forever, printing each message as it arrives.
	for {
		msg, err := readMessage(reader)
		if err != nil {
			log.Fatalf("read failed: %v", err)
		}
		printMessage(msg)
	}
}

// readMessage fetches the next message from the topic.
// It blocks until a message is available.
func readMessage(reader *kafkalib.Reader) (kafkalib.Message, error) {
	return reader.ReadMessage(context.Background())
}

// printMessage displays a consumed message with its partition and offset.
func printMessage(msg kafkalib.Message) {
	fmt.Printf("partition=%d offset=%d | %s\n",
		msg.Partition, msg.Offset, string(msg.Value))
}
