from confluent_kafka import Consumer
import os
import json
from producer_handler import KafkaProducer
from text_handler import get_instructions, clean_text

KAFKA_LISTEN_TOPIC = os.getenv("KAFKA_LISTEN_TOPIC")
BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID")

# ========================================================================
# SETTING KAFKA CONSUMER
# ========================================================================

consumer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "group.id": KAFKA_GROUP_ID,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
}

consumer = Consumer(consumer_config)
consumer.subscribe([KAFKA_LISTEN_TOPIC])

producer = KafkaProducer()

# ========================================================================
# MAIN LOOP
# ========================================================================

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("❌ Error:", msg.error())
        continue
    value = msg.value().decode("utf-8")
    order = json.loads(value)

    # cleaning instructions and preperations
    cleaned_instruction = clean_text(order["special_instructions"])
    cleaned_prep_instructions = clean_text(get_instructions(order["pizza_type"]))

    cleaned_instruction = {
        "order_id": order["order_id"],
        "pizza_type": order["pizza_type"],
        "special_instructions": cleaned_instruction,
        "prep_instructions": cleaned_prep_instructions
    }

    # sending to kafka
    producer.send_orders_to_kafka(cleaned_instruction)
