"""
Reads values coming in off the kafka queue and pushes them to Cloudwatch for
as a first effort in graphing
"""

import json
import boto3
from kafka.errors import KafkaError, NoBrokersAvailable
import kafka_consume as kafka_cons
import os
import time

METRIC_NAMES = [
    "baro_temp_celcius",
    "humidity",
    "light",
    "pressure_pa",
    "temp_celcius",
    "mq135",
    "mq5",
    "mq6",
    "mq9",
]

def valid_metric(metric_name, value):
    """Validates that a metric is within reasonable, reportable parameters.
    Returns True if valid (default) and false if any validity constraints are
    violated. A very hacky, first effort, implementation"""

    # by default, all metrics less than 0 are considered invalid values
    if value < 0:
        return False

    if "mq" in metric_name and value > 1000:
        return False

    return True

def make_metrics(values):
    """Creates a list of metrics to push to Cloudwatch"""

    metrics = []
    for metric in METRIC_NAMES:
        if valid_metric(metric, values[metric]):
            metrics.append({
                "MetricName": metric,
                "Dimensions": [
                    {
                        "Name": "Device Metrics",
                        "Value": "nycWeather001"
                        },
                    ],
                "Timestamp": values["capture_dttm"],
                "Value": values[metric],
                "Unit": "None"
                })
    return metrics


def index_in_cloudwatch(event):
    """Main event processor. Reads message off of Kafka queue, makes calls to
    check the validity of the values of the message (wrt Cloudwatch), creates
    metrics and pushes them to Cloudwatch"""

    values = json.loads(event)
    client = boto3.client("cloudwatch")

    metrics = make_metrics(values)
    response = client.put_metric_data(
        Namespace="weatherIoT",
        MetricData=metrics
    )
    print("Request: %s" % json.dumps(metrics))
    print("Response: %s" % response)

    if not response["ResponseMetadata"]["HTTPStatusCode"] == 200:
        index_in_cloudwatch(event)


if __name__ == '__main__':
    attempts = 0
    max_attempts = os.environ.get('MAX_CONNECTION_RETRIES', 10)

    while(attempts < int(max_attempts)):
        try:
            consumer_group = "weather_consumer_cw"
            consumer_device = "weather_consumer_cw_%s" % os.getenv("HOSTNAME",
                                                                   "001")
            kafka_topic = "weather"

            consumer = kafka_cons.start_consumer(consumer_group,
                                                 consumer_device,
                                                 kafka_topic,
                                                 # this will start consuming at
                                                 # the most recent. If offline,
                                                 # old messages will not be
                                                 # consumed
                                                 auto_offset_reset='latest')
            print("Starting consumer")
            for message in consumer:
                print(message.value.decode("utf-8"))
                index_in_cloudwatch(message.value.decode("utf-8"))

        except NoBrokersAvailable:
            print("No Brokers. Attempt %s" % attempts)
            attempts = attempts + 1
            time.sleep(2)
