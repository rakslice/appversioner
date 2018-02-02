import json


def read_json(filename):
    with open(filename, "rb") as handle:
        return json.load(handle)


