import json
import subprocess
import os
from queue import Queue
import threading
import psycopg2
import datetime
from tools import hash_str, version_to_int

stop = False
message_encoding = 'utf-8'

expected_info_dict = [
    {'aws_name': 'user_id', 'sql_name': 'user_id', 'type': str, 'process': None, 'required': True},
    {'aws_name': 'device_type', 'sql_name': 'device_type', 'type': str, 'process': None, 'required': True},
    {'aws_name': 'ip', 'sql_name': 'masked_ip', 'type': str, 'process': hash_str, 'required': True},
    {'aws_name': 'device_id', 'sql_name': 'masked_device_id', 'type': str, 'process': hash_str, 'required': True},
    {'aws_name': 'locale', 'sql_name': 'locale', 'type': str, 'process': None, 'required': True},
    {'aws_name': 'app_version', 'sql_name': 'app_version', 'type': int, 'process': version_to_int, 'required': True},
    {'aws_name': 'create_date', 'sql_name': 'create_date', 'type': str, 'process': datetime.date.today,
     'required': False},
]

queue_url = 'http://localhost:4566/000000000000/login-queue'


def exit_handler(error_code):
    global stop
    stop = True
    print("Exiting...")
    exit(error_code)


def get_insert_query() -> str:
    insert_query = "INSERT INTO user_logins ("
    for ele in expected_info_dict:
        key = ele['sql_name']
        insert_query += key + ", "

    insert_query = insert_query[:-2] + ") VALUES ("
    for ele in expected_info_dict:
        insert_query += "%s, "

    insert_query = insert_query[:-2] + ")"
    print(insert_query)
    return insert_query


def get_from_aws(queue: Queue):
    # Set environment variable in case ssh connection do not load it
    os.environ["LOCALSTACK_HOST"] = "localstack"

    while not stop:
        # Execute aws command:
        #   awslocal sqs receive-message --queue-url {queue_url}

        raw_value = subprocess.run(['awslocal', 'sqs', 'receive-message', '--queue-url', queue_url],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        is_correct = True
        if raw_value.returncode != 0:
            print("Error getting message from AWS")
            print(raw_value.stderr.decode(message_encoding))
            exit_handler(1)
        else:
            stdout = raw_value.stdout.decode(message_encoding)
            try:
                json_obj = json.loads(stdout)
                body = json_obj['Messages'][0]['Body']
                body = json.loads(body)
            except Exception as e:
                print("Error parsing message from AWS")
                print(e)
                print(stdout)
                continue

            out_dict = {}
            for ele in expected_info_dict:
                aws_key = ele['aws_name']
                sql_key = ele['sql_name']
                process_func = ele['process']
                if ele['required']:
                    if aws_key not in body:
                        # Exit before reading more messages
                        print("Error: missing key: " + aws_key)
                        print("Wrong message format")
                        print(stdout)
                        is_correct = False
                        break
                    else:
                        if process_func is not None:
                            out_dict[sql_key] = process_func(body[aws_key])
                        else:
                            out_dict[sql_key] = body[aws_key]
                else:
                    out_dict[sql_key] = process_func()

            if is_correct:
                queue.put(out_dict)


def write_to_sql(queue: Queue, connection: psycopg2.connect):
    insert_query = get_insert_query()

    while not stop:
        message = queue.get()
        print(message)

        record_to_insert = []
        for ele in expected_info_dict:
            key = ele['sql_name']
            record_to_insert.append(message[key])
        # change to tuple
        record_to_insert = tuple(record_to_insert)
        cursor = connection.cursor()
        cursor.execute(insert_query, record_to_insert)
        connection.commit()


def app():
    # Create worker threads
    queue = Queue()
    postsql_connection = None
    try:
        print("Connecting to postgreSQL")
        postsql_connection = psycopg2.connect("dbname=postgres user=postgres password=postgres host=postgres")
    except Exception as e:
        print("Error connecting to postgreSQL: " + str(e))
        if postsql_connection is not None:
            postsql_connection.close()
        print("Exit with Error")
        exit(1)

    producer = threading.Thread(target=get_from_aws, args=(queue,))
    consumer = threading.Thread(target=write_to_sql, args=(queue, postsql_connection,))

    # Setting daemon to True will let the main thread exit even though the workers are blocking
    producer.daemon = True
    consumer.daemon = True
    producer.start()
    consumer.start()

    # Wait for the worker to finish
    producer.join()
    consumer.join()
    postsql_connection.close()


# %%
if __name__ == '__main__':
    app()
