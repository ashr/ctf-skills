#!/usr/bin/env python3
"""Burp-oriented helper client for agent workflows.

This utility does not call Burp internal APIs directly. It standardizes common
workflows that route traffic through a Burp proxy:
1) proxied HTTP requests,
2) directory bruteforce via ffuf,
3) static (retire.js) and dynamic (nuclei) scans.

All commands emit JSON to stdout for easy agent consumption.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass
class BurpClientConfig:
    proxy_url: str | None = None
    api_base_url: str | None = None
    timeout_seconds: int = 30


class BurpAgentClient:
    def __init__(self, config: BurpClientConfig) -> None:
        self.config = config

    def _proxies(self) -> dict[str, str] | None:
        if not self.config.proxy_url:
            return None
        return {
            "http": self.config.proxy_url,
            "https": self.config.proxy_url,
        }

    def burp_api_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout_seconds: int | None = None,
        verify_tls: bool = True,
    ) -> dict[str, Any]:
        if not self.config.api_base_url:
            raise ValueError("Burp API base URL is not configured. Use --api-base-url or BURP_API_BASE_URL.")

        timeout = timeout_seconds or self.config.timeout_seconds
        base_url = self.config.api_base_url.rstrip("/")
        request_path = path if path.startswith("/") else f"/{path}"
        url = f"{base_url}{request_path}"

        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            data=body,
            timeout=timeout,
            verify=verify_tls,
            allow_redirects=False,
        )

        content_type = response.headers.get("content-type", "")
        parsed_body: Any
        if "application/json" in content_type.lower():
            try:
                parsed_body = response.json()
            except ValueError:
                parsed_body = response.text
        else:
            parsed_body = response.text

        return {
            "ok": True,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": parsed_body,
            "url": response.url,
        }

    def proxied_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout_seconds: int | None = None,
        verify_tls: bool = True,
    ) -> dict[str, Any]:
        timeout = timeout_seconds or self.config.timeout_seconds
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            data=body,
            proxies=self._proxies(),
            timeout=timeout,
            verify=verify_tls,
            allow_redirects=False,
        )

        return {
            "ok": True,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
            "url": response.url,
        }

    def directory_bruteforce(
        self,
        url_template: str,
        wordlist: str,
        extensions: str = "",
        match_codes: str = "200,204,301,302,307,401,403",
        filter_codes: str = "",
        threads: int = 40,
        rate: int = 0,
    ) -> dict[str, Any]:
        cmd = [
            "ffuf",
            "-u",
            url_template,
            "-w",
            wordlist,
            "-of",
            "json",
            "-mc",
            match_codes,
            "-t",
            str(threads),
        ]
        if extensions:
            cmd.extend(["-e", extensions])
        if filter_codes:
            cmd.extend(["-fc", filter_codes])
        if rate > 0:
            cmd.extend(["-rate", str(rate)])
        if self.config.proxy_url:
            cmd.extend(["-x", self.config.proxy_url])

        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)

        stdout = completed.stdout.strip()
        parsed: dict[str, Any]
        if stdout:
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError:
                parsed = {"raw_stdout": stdout}
        else:
            parsed = {}

        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "command": shlex.join(cmd),
            "result": parsed,
            "stderr": completed.stderr,
        }

    def dynamic_scan(
        self,
        targets: list[str],
        severities: str = "critical,high,medium,low,info",
        templates: str = "",
    ) -> dict[str, Any]:
        cmd = [
            "nuclei",
            "-silent",
            "-jsonl",
            "-severity",
            severities,
        ]
        if templates:
            cmd.extend(["-t", templates])
        for target in targets:
            cmd.extend(["-u", target])
        if self.config.proxy_url:
            cmd.extend(["-proxy", self.config.proxy_url])

        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)

        findings: list[dict[str, Any]] = []
        for line in completed.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                findings.append(json.loads(line))
            except json.JSONDecodeError:
                findings.append({"raw": line})

        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "command": shlex.join(cmd),
            "findings": findings,
            "stderr": completed.stderr,
        }

    def static_scan(self, url: str) -> dict[str, Any]:
        cmd = ["retire", "--url", url, "--outputformat", "json"]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)

        raw_stdout = completed.stdout.strip()
        parsed: Any = {}
        if raw_stdout:
            try:
                parsed = json.loads(raw_stdout)
            except json.JSONDecodeError:
                parsed = {"raw_stdout": raw_stdout}

        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "command": shlex.join(cmd),
            "result": parsed,
            "stderr": completed.stderr,
        }

    def preflight(self, test_url: str = "https://example.com", mode: str = "proxy") -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        mode = mode.strip().lower()
        if mode not in {"proxy", "proxy_and_api", "api_only"}:
            raise ValueError("Invalid preflight mode. Use one of: proxy, proxy_and_api, api_only")

        require_proxy = mode in {"proxy", "proxy_and_api"}
        require_api = mode in {"proxy_and_api", "api_only"}

        proxy_ok = True
        api_ok = True

        if self.config.proxy_url:
            proxy_check: dict[str, Any] = {
                "name": "proxy_reachability",
                "target": self.config.proxy_url,
            }
            try:
                response = requests.get(
                    test_url,
                    proxies=self._proxies(),
                    timeout=self.config.timeout_seconds,
                    allow_redirects=False,
                )
                proxy_check.update(
                    {
                        "ok": True,
                        "required": require_proxy,
                        "status_code": response.status_code,
                        "test_url": test_url,
                    }
                )
            except requests.RequestException as exc:
                proxy_check.update(
                    {
                        "ok": False,
                        "required": require_proxy,
                        "error": str(exc),
                        "test_url": test_url,
                    }
                )
                proxy_ok = False
            checks.append(proxy_check)
        else:
            proxy_ok = False
            checks.append(
                {
                    "name": "proxy_reachability",
                    "ok": False,
                    "required": require_proxy,
                    "skipped": True,
                    "reason": "No proxy configured (use --proxy-url or BURP_PROXY_URL).",
                }
            )

        if self.config.api_base_url:
            api_check: dict[str, Any] = {
                "name": "burp_api_reachability",
                "target": self.config.api_base_url,
            }
            try:
                response = requests.get(
                    self.config.api_base_url.rstrip("/") + "/health",
                    timeout=self.config.timeout_seconds,
                    allow_redirects=False,
                )
                api_check.update(
                    {
                        "ok": True,
                        "required": require_api,
                        "status_code": response.status_code,
                        "path": "/health",
                    }
                )
            except requests.RequestException as exc:
                api_check.update(
                    {
                        "ok": False,
                        "required": require_api,
                        "error": str(exc),
                        "path": "/health",
                    }
                )
                api_ok = False
            checks.append(api_check)
        else:
            api_ok = False
            checks.append(
                {
                    "name": "burp_api_reachability",
                    "ok": False,
                    "required": require_api,
                    "skipped": True,
                    "reason": "No API base URL configured (use --api-base-url or BURP_API_BASE_URL).",
                }
            )

        proxy_failed = require_proxy and not proxy_ok
        api_failed = require_api and not api_ok

        if not proxy_failed and not api_failed:
            exit_code = 0
        elif proxy_failed and api_failed:
            exit_code = 22
        elif proxy_failed:
            exit_code = 20
        else:
            exit_code = 21

        return {
            "ok": exit_code == 0,
            "mode": mode,
            "exit_code": exit_code,
            "checks": checks,
        }


def parse_headers(items: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in items:
        if ":" not in item:
            raise ValueError(f"Invalid header format: {item}. Use 'Key: Value'.")
        key, value = item.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Burp-oriented agent helper client")
    parser.add_argument("--proxy-url", default="", help="Proxy URL, e.g. http://172.17.0.1:8080")
    parser.add_argument("--api-base-url", default="", help="Burp API base URL, e.g. http://172.17.0.1:1337")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")

    subparsers = parser.add_subparsers(dest="command", required=True)

    req_parser = subparsers.add_parser("proxy-request", help="Send HTTP request through proxy")
    req_parser.add_argument("--method", required=True)
    req_parser.add_argument("--url", required=True)
    req_parser.add_argument("--header", action="append", default=[])
    req_parser.add_argument("--body", default="")
    req_parser.add_argument("--insecure", action="store_true", help="Disable TLS verification")

    brute_parser = subparsers.add_parser("dir-brute", help="Run ffuf directory bruteforce")
    brute_parser.add_argument("--url-template", required=True, help="Include FUZZ, e.g. https://target/FUZZ")
    brute_parser.add_argument("--wordlist", required=True)
    brute_parser.add_argument("--extensions", default="")
    brute_parser.add_argument("--match-codes", default="200,204,301,302,307,401,403")
    brute_parser.add_argument("--filter-codes", default="")
    brute_parser.add_argument("--threads", type=int, default=40)
    brute_parser.add_argument("--rate", type=int, default=0)

    dyn_parser = subparsers.add_parser("dynamic-scan", help="Run nuclei dynamic scan")
    dyn_parser.add_argument("--target", action="append", required=True)
    dyn_parser.add_argument("--severities", default="critical,high,medium,low,info")
    dyn_parser.add_argument("--templates", default="")

    static_parser = subparsers.add_parser("static-scan", help="Run retire.js on target URL")
    static_parser.add_argument("--url", required=True)

    burp_api_parser = subparsers.add_parser("burp-api-request", help="Send request to Burp API endpoint")
    burp_api_parser.add_argument("--method", required=True)
    burp_api_parser.add_argument("--path", required=True, help="API path, e.g. /health")
    burp_api_parser.add_argument("--header", action="append", default=[])
    burp_api_parser.add_argument("--body", default="")
    burp_api_parser.add_argument("--insecure", action="store_true", help="Disable TLS verification")

    preflight_parser = subparsers.add_parser("preflight", help="Verify Burp proxy/API connectivity")
    preflight_parser.add_argument("--test-url", default="https://example.com", help="URL for proxy reachability check")
    preflight_parser.add_argument(
        "--mode",
        choices=["proxy", "proxy_and_api", "api_only"],
        default="proxy",
        help="Preflight policy mode (default: proxy)",
    )

    args = parser.parse_args()

    proxy_url = args.proxy_url or os.getenv("BURP_PROXY_URL", "")
    api_base_url = args.api_base_url or os.getenv("BURP_API_BASE_URL", "")

    config = BurpClientConfig(
        proxy_url=proxy_url or None,
        api_base_url=api_base_url or None,
        timeout_seconds=args.timeout,
    )
    client = BurpAgentClient(config)

    try:
        if args.command == "proxy-request":
            payload = client.proxied_request(
                method=args.method,
                url=args.url,
                headers=parse_headers(args.header),
                body=args.body,
                verify_tls=not args.insecure,
            )
        elif args.command == "dir-brute":
            wordlist_path = Path(args.wordlist)
            if not wordlist_path.exists():
                return _emit_error(f"Wordlist not found: {wordlist_path}")
            payload = client.directory_bruteforce(
                url_template=args.url_template,
                wordlist=str(wordlist_path),
                extensions=args.extensions,
                match_codes=args.match_codes,
                filter_codes=args.filter_codes,
                threads=args.threads,
                rate=args.rate,
            )
        elif args.command == "dynamic-scan":
            payload = client.dynamic_scan(
                targets=args.target,
                severities=args.severities,
                templates=args.templates,
            )
        elif args.command == "static-scan":
            payload = client.static_scan(url=args.url)
        elif args.command == "burp-api-request":
            payload = client.burp_api_request(
                method=args.method,
                path=args.path,
                headers=parse_headers(args.header),
                body=args.body,
                verify_tls=not args.insecure,
            )
        elif args.command == "preflight":
            payload = client.preflight(test_url=args.test_url, mode=args.mode)
        else:
            return _emit_error(f"Unknown command: {args.command}")
    except requests.RequestException as exc:
        return _emit_error(f"Request failed: {exc}")
    except ValueError as exc:
        return _emit_error(str(exc))

    print_json(payload)
    if args.command == "preflight":
        return int(payload.get("exit_code", 1))
    return 0 if payload.get("ok", False) else 1


def _emit_error(message: str) -> int:
    print_json({"ok": False, "error": message})
    return 1


if __name__ == "__main__":
    sys.exit(main())
