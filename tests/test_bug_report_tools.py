from service.integrations.bug_report_tools import BugReportTools


class FakeRowConnection:
    def __init__(self, row):
        self.row = row
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((query, params))
        return self

    def fetchone(self):
        return self.row


class FakeConnectionManager:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDB:
    def __init__(self, row):
        self.row = row
        self.last_connection = None

    def connect(self):
        self.last_connection = FakeRowConnection(self.row)
        return FakeConnectionManager(self.last_connection)


class FakeBugReportsRepo:
    def __init__(self, primary_client_row, report):
        self.db = FakeDB(primary_client_row)
        self._report = report
        self.created_reports = []

    def create_report(self, **kwargs):
        self.created_reports.append(kwargs)
        return {
            "report_id": "report-1234",
            "title": kwargs["title"],
            "summary": kwargs["summary"],
            "details": kwargs["details"],
            "client": kwargs["client"],
            "client_id": kwargs["client_id"],
            "metadata": kwargs.get("metadata", {}),
            "status": "pending",
            "codey_status": None,
            "codey_task_id": None,
        }

    def get_report(self, report_id):
        return self._report

    def list_reports(self, **kwargs):
        return [self._report]


class FakeCodeyProcessor:
    def __init__(self):
        self.calls = []

    def submit_to_codey(self, **kwargs):
        self.calls.append(kwargs)
        return {"task_id": "codey-task-1", "status": "queued"}


def test_submit_bug_report_uses_opened_connection_and_primary_client_id():
    repo = FakeBugReportsRepo(
        primary_client_row={"client_id": "client-123"},
        report={
            "report_id": "report-xyz",
            "title": "Broken sync",
            "summary": "Broken sync",
            "details": "Sync fails",
            "client": "alfred-android",
            "client_id": "client-123",
            "metadata": {},
            "status": "pending",
            "codey_status": None,
            "codey_task_id": None,
        },
    )
    processor = FakeCodeyProcessor()
    tools = BugReportTools(repo, processor)

    bug = tools.submit_bug_report(
        title="Broken sync",
        summary="Broken sync",
        details="Sync fails",
        client="alfred-android",
        metadata={"device": "pixel"},
    )

    assert repo.db.last_connection is not None
    assert repo.db.last_connection.queries[0][0] == "SELECT client_id FROM clients WHERE is_primary = 1 LIMIT 1"
    assert repo.created_reports[0]["client_id"] == "client-123"
    assert processor.calls[0]["client_id"] == "client-123"
    assert bug["client_id"] == "client-123"


def test_forward_to_codey_preserves_client_id_from_bug_payload():
    repo = FakeBugReportsRepo(
        primary_client_row={"client_id": "client-123"},
        report={
            "report_id": "report-xyz",
            "title": "Broken sync",
            "summary": "Broken sync",
            "details": "Sync fails",
            "client": "alfred-android",
            "client_id": "client-123",
            "metadata": {"device": "pixel"},
            "status": "pending",
            "codey_status": None,
            "codey_task_id": None,
        },
    )
    processor = FakeCodeyProcessor()
    tools = BugReportTools(repo, processor)

    task = tools.forward_to_codey("report-xyz")

    assert task == {"task_id": "codey-task-1", "status": "queued"}
    assert processor.calls[0]["client_id"] == "client-123"
    assert processor.calls[0]["metadata"] == {"device": "pixel"}
