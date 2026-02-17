from confluent_kafka import Consumer
import os
import json
import logging
from producer_handler import KafkaProducer
from text_handler import get_instructions, clean_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_LISTEN_TOPIC = os.getenv("KAFKA_LISTEN_TOPIC")
BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID")

consumer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "group.id": KAFKA_GROUP_ID,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
}

consumer = Consumer(consumer_config)
consumer.subscribe([KAFKA_LISTEN_TOPIC])

producer = KafkaProducer()

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("❌ Error:", msg.error())
        continue
    value = msg.value().decode("utf-8")
    order = json.loads(value)
    logger.info(order)

    #
    cleaned_instruction = clean_text(order["special_instructions"])
    cleaned_prep_instructions = clean_text(get_instructions(order["pizza_type"]))

    logger.info(cleaned_instruction)
    logger.info(cleaned_prep_instructions)

    cleaned_instruction = {
        "order_id": order["order_id"],
        "pizza_type": order["pizza_type"],
        "special_instructions": cleaned_instruction,
        "prep_instructions": cleaned_prep_instructions
    }
    producer.send_orders_to_kafka(cleaned_instruction)
