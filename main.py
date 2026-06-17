import json
import sys
import os
from collections import Counter

import requests
from specklepy.api.client import SpeckleClient
from specklepy.transports.server import ServerTransport
from specklepy.api import operations

os.environ["SPECKLEPY_DISABLE_ANALYTICS"] = "true"

REPORT_MUTATION = """
mutation Report($input: AutomateFunctionRunStatusReportInput!) {
  automateFunctionRunStatusReport(input: $input)
}
"""

VERSION_QUERY = """
query GetVersion($projectId: String!, $versionId: String!) {
  project(id: $projectId) {
    version(id: $versionId) {
      referencedObject
    }
  }
}
"""


def report(server_url, token, project_id, function_run_id, status, message=None):
    try:
        res = requests.post(
            f"{server_url}/graphql",
            json={"query": REPORT_MUTATION, "variables": {"input": {"projectId": project_id, "functionRunId": function_run_id, "status": status, "statusMessage": message}}},
            headers={"Authorization": f"Bearer {token}", "apollographql-client-name": "automate-function"},
            timeout=30,
        )
        data = res.json()
        if "errors" in data:
            print(f"[function] GraphQL errors: {data['errors']}")
        else:
            print(f"[function] Reported status={status}")
    except Exception as e:
        print(f"[function] Failed to report status: {e}")


def get_speckle_type(obj):
    t = getattr(obj, "speckle_type", None)
    return t.split(".")[-1] if t else "Unknown"


def walk_objects(obj, counter, visited):
    obj_id = getattr(obj, "id", None)
    if obj_id is not None:
        if obj_id in visited:
            return
        visited.add(obj_id)
    t = getattr(obj, "speckle_type", None)
    if t and t != "Base":
        counter[get_speckle_type(obj)] += 1
    for name in getattr(obj, "get_member_names", lambda: [])():
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if hasattr(value, "speckle_type"):
            walk_objects(value, counter, visited)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if hasattr(item, "speckle_type"):
                    walk_objects(item, counter, visited)
        elif isinstance(value, dict):
            for item in value.values():
                if hasattr(item, "speckle_type"):
                    walk_objects(item, counter, visited)


def run(input_path):
    with open(input_path) as f:
        data = json.load(f)

    token = data["speckleToken"]
    run_data = data["automationRunData"]
    server_url = run_data["speckleServerUrl"]
    server_url = server_url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
    project_id = run_data["projectId"]
    function_run_id = run_data["functionRunId"]
    trigger = run_data["triggers"][0]
    version_id = trigger["payload"]["versionId"]
    model_id = trigger["payload"]["modelId"]

    print(f"[function] project={project_id} model={model_id} version={version_id} server={server_url}")
    report(server_url, token, project_id, function_run_id, "RUNNING", "Fetching model data")

    try:
        # Get referencedObject via GraphQL
        res = requests.post(
            f"{server_url}/graphql",
            json={"query": VERSION_QUERY, "variables": {"projectId": project_id, "versionId": version_id}},
            headers={"Authorization": f"Bearer {token}", "apollographql-client-name": "automate-function"},
            timeout=30,
        )
        gql_data = res.json()
        referenced_object_id = gql_data["data"]["project"]["version"]["referencedObject"]
        print(f"[function] referencedObject={referenced_object_id}")

        client = SpeckleClient(host=server_url, use_ssl=False)
        client.authenticate_with_token(token)

        transport = ServerTransport(client=client, stream_id=project_id)
        root_object = operations.receive(referenced_object_id, transport)

        counter = Counter()
        visited = set()
        walk_objects(root_object, counter, visited)

        total = sum(counter.values())
        if total == 0:
            summary = "No categorized elements found."
        else:
            top = ", ".join(f"{n}: {c}" for n, c in counter.most_common(10))
            summary = f"Found {total} elements across {len(counter)} categories. {top}"

        print(f"[function] {summary}")
        report(server_url, token, project_id, function_run_id, "SUCCEEDED", summary)

    except Exception as e:
        msg = f"Function failed: {e}"
        print(f"[function] {msg}")
        report(server_url, token, project_id, function_run_id, "FAILED", msg)
        sys.exit(1)


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/input.json"
    run(input_file)
