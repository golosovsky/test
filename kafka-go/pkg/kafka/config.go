// Package kafka provides shared configuration and helpers for
// connecting to a Kafka broker with sensible defaults.
package kafka

import (
	"time"

	kafkalib "github.com/segmentio/kafka-go"
)

// Defaults — single place to tweak broker address, topic, etc.
const (
	Broker  = "localhost:9092"
	Topic   = "messages"
	GroupID = "my-group" // consumer group for offset tracking
)

// NewWriter creates a Kafka producer targeting the configured topic.
// Balancer round-robins messages across partitions.
func NewWriter() *kafkalib.Writer {
	return &kafkalib.Writer{
		Addr:         kafkalib.TCP(Broker),
		Topic:        Topic,
		Balancer:     &kafkalib.LeastBytes{}, // spread load evenly
		BatchTimeout: 10 * time.Millisecond,  // low latency for demos
	}
}

// NewReader creates a Kafka consumer for the configured topic + group.
// The consumer group tracks offsets so restarts resume where they left off.
func NewReader() *kafkalib.Reader {
	return kafkalib.NewReader(kafkalib.ReaderConfig{
		Brokers: []string{Broker},
		Topic:   Topic,
		GroupID: GroupID,
	})
}
