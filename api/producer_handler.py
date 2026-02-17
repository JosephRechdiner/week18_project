from confluent_kafka import Producer
import json
import os

BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC")

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
        
    def send_orders_to_kafka(self, orders: list[dict], topic: str = KAFKA_TOPIC): 
        for order in orders:
            try:
                self.producer.produce(topic, value=json.dumps(order).encode("utf-8"))
            except Exception as e:
                raise Exception(f"Could not send {order} to kafka, Error: {str(e)}")
        self.producer.flush()
        return f"All data sent to kafka"



