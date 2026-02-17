from confluent_kafka import Producer
import json
import os

BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_SEND_TOPIC = os.getenv("KAFKA_SEND_TOPIC")

producer_config = {"bootstrap.servers": BOOTSTRAP_SERVERS}

class KafkaProducer:
    producer = None
    def __init__(self):
        try:
            if not KafkaProducer.producer:
                KafkaProducer.producer = Producer(producer_config)
            self.producer = KafkaProducer.producer
        except Exception as e:
            raise Exception(f"Could not init kafka producer, Error: {str(e)}")
        
    def send_orders_to_kafka(self, order_details, topic: str = KAFKA_SEND_TOPIC): 
        try:
            self.producer.produce(topic, value=json.dumps(order_details).encode("utf-8"))
            self.producer.flush()
        except Exception as e:
            raise Exception(f"Could not send {order_details} to kafka, Error: {str(e)}")
        return f"All data sent to kafka"