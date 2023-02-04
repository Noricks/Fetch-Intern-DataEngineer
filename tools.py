from cryptography.fernet import Fernet
import logging

key = b'qaOMUbtW4M31PDU8p0LdwTdgE22coHm00RGOFK-FSQs='


def encode_str(value: str) -> str:
    f = Fernet(key)
    return f.encrypt(value.encode()).decode()


def decode_str(value: str) -> str:
    f = Fernet(key)
    return f.decrypt(value.encode()).decode()


def version_to_int(version: str) -> int:
    version = version.split('.')
    version.reverse()
    version_value = 0
    base = 0
    while len(version) < 3:
        version.append('0')
    for e in version:
        version_value += int(e) * pow(2, base)
        base += 4
    return version_value


class ServiceExit(Exception):
    """
    Custom exception which is used to trigger the clean exit
    of all running threads and the main program.
    """
    pass


def signal_handler(sig, frame):
    logging.info('Caught signal: ' + str(sig))
    raise ServiceExit
