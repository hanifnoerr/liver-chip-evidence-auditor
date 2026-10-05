"""Serve the offline viewer and fit an albumin CSV on the local CPU."""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Lock
import argparse
import csv
import io
import json

from auditor import analyse_evidence
from followthrough import reassess_case
from small_model.planner import evidence_packet, eligible_actions, guard_action, render_action, rule_action

ROOT = Path(__file__).resolve().parent


class DemoHandler(SimpleHTTPRequestHandler):
    action_model = None
    action_model_lock = Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path == "/reassess":
            try:
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                result = reassess_case(payload["baseline_records"], payload["updated_csv"], payload["evidence_reference"], payload["compatibility_note"], payload["delivered_action"], payload.get("action_doses", []))
                self.respond_json(result)
            except (KeyError, ValueError, TypeError) as error:
                self.respond_json({"error": str(error)}, 400)
            return
        if self.path == "/plan":
            self.plan_action()
            return
        if self.path != "/audit":
            self.send_error(404)
            return
        try:
            text = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8-sig")
            records = []
            for row in csv.DictReader(io.StringIO(text)):
                if row["endpoint"] != "albumin_percent":
                    continue
                row["missing"] = row["missing"].lower() in ["true", "1"]
                row["dose_cmax_multiple"] = float(row["dose_cmax_multiple"])
                row["value"] = "" if row["missing"] else float(row["value"])
                records.append(row)
            if not records:
                raise ValueError("The CSV contains no albumin_percent records.")
            results = []
            for compound in sorted(set(row["compound"] for row in records)):
                subset = [row for row in records if row["compound"] == compound]
                result = analyse_evidence(subset)
                if result["blocked"]:
                    messages = [issue["message"] for issue in result["issues"] if issue["severity"] == "blocked"]
                    raise ValueError(compound + ": " + " ".join(messages))
                result["compound"] = compound
                result["records"] = subset
                results.append(result)
            body = json.dumps(results, allow_nan=False).encode("utf-8")
            status = 200
        except (KeyError, ValueError) as error:
            body = json.dumps({"error": str(error)}).encode("utf-8")
            status = 400
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/planner-status":
            self.respond_json({"model_loaded": self.action_model is not None, "model": str(self.action_model.model_path) if self.action_model else None, "status": "experimental"})
            return
        super().do_GET()

    def respond_json(self, value, status=200):
        body = json.dumps(value, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def plan_action(self):
        try:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            request = payload["request"]
            if not isinstance(request, str) or not 1 <= len(request.strip()) <= 1000:
                raise ValueError("Enter a request between 1 and 1000 characters.")
            resources = payload["resources"]
            for name in ["record_review", "missing_record_access", "new_dose_allowed"]:
                if not isinstance(resources[name], bool):
                    raise ValueError("Resource settings must be true or false.")
            if type(resources["repeat_budget"]) is not int or resources["repeat_budget"] not in [0, 1]:
                raise ValueError("This experiment supports zero or one independent repeat.")
            records = payload["records"]
            if not isinstance(records, list) or not records:
                raise ValueError("Source records are required.")
            analysis = analyse_evidence(records)
            analysis["records"] = records
            analysis["compound"] = records[0]["compound"]
            packet = evidence_packet(analysis)
            engine = payload.get("engine", "rules")
            if engine not in ["rules", "model"]:
                raise ValueError("Choose rules or the local model.")
            if engine == "model" and self.action_model is None:
                self.respond_json({"error": "No language model is loaded. Start demo.py with --model pointing to a trained local checkpoint; see Guide for setup."}, 503)
                return
            details = {}
            if engine == "model":
                with self.action_model_lock:
                    raw, details = self.action_model.choose(packet, request, resources)
            else:
                raw = rule_action(packet, request, resources)
            delivered, fallback = guard_action(raw, packet, request, resources)
            action = render_action(delivered, analysis, resources)
            self.respond_json({"engine": engine, "raw_action": raw, "delivered_action": delivered, "fallback": fallback, "allowed_actions": eligible_actions(packet, resources), "action": action, "inference": details, "experimental": True, "audit": analysis})
        except (KeyError, ValueError, TypeError) as error:
            self.respond_json({"error": str(error)}, 400)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Optional local action-model checkpoint; use its own environment.")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if args.model:
        from small_model.model_runtime import ActionModel
        DemoHandler.action_model = ActionModel(args.model, device="cpu", threads=args.threads)
    print(f"Open http://127.0.0.1:{args.port}/auditor_demo.html", flush=True)
    print(f"Action-planner experiment: http://127.0.0.1:{args.port}/planner.html", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler).serve_forever()
