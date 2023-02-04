import hashlib


def hash_str(value) -> str:
    value = str(value)
    sha256 = hashlib.sha256()
    sha256.update(value.encode('utf-8'))
    res = sha256.hexdigest()
    return res


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
