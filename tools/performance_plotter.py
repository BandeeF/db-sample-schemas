#!/usr/bin/env python3
"""
Collect short performance samples with pidstat and render them into an HTML report
with simple CPU and memory plots powered by Chart.js.
"""
import argparse
import html
import json
import subprocess
from pathlib import Path


TABLE_COLUMNS = (
    "time",
    "uid",
    "pid",
    "usr_pct",
    "system_pct",
    "guest_pct",
    "cpu_pct",
    "cpu",
    "minflt_s",
    "majflt_s",
    "vsz",
    "rss",
    "mem_pct",
    "kb_rd_s",
    "kb_wr_s",
    "kb_ccwr_s",
    "iodelay",
)


def parse_pidstat_output(stdout: str) -> list[dict[str, str]]:
    """Parse pidstat output rows into a list of dictionaries."""
    rows: list[dict[str, str]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("Linux", "#", "Average:")):
            continue
        parts = stripped.split()
        if len(parts) < len(TABLE_COLUMNS):
            continue
        row = dict(zip(TABLE_COLUMNS, parts))
        rows.append(row)
    return rows


def run_pidstat(pid: int | None, interval: int, count: int) -> str:
    """Execute pidstat and return its stdout."""
    pid_arg = "ALL" if pid is None else str(pid)
    command = [
        "pidstat",
        "-durh",
        "-p",
        pid_arg,
        str(interval),
        str(count),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout


def build_html(
    rows: list[dict[str, str]],
    raw_output: str,
    pid: int | None,
    interval: int,
    count: int,
    title: str,
) -> str:
    aggregated: dict[str, dict[str, float]] = {}
    time_order: list[str] = []
    for row in rows:
        time_key = row["time"]
        cpu = float(row["cpu_pct"])
        mem = float(row["mem_pct"])
        if time_key not in aggregated:
            aggregated[time_key] = {"cpu": 0.0, "mem": 0.0}
            time_order.append(time_key)
        aggregated[time_key]["cpu"] += cpu
        aggregated[time_key]["mem"] += mem

    times = time_order
    cpu_values = [aggregated[t]["cpu"] for t in times]
    mem_values = [aggregated[t]["mem"] for t in times]

    escaped_raw_output = html.escape(raw_output)
    row_cells = "\n".join(
        f"<tr><td>{html.escape(row['time'])}</td><td>{html.escape(row['pid'])}</td><td>{html.escape(row['cpu_pct'])}</td><td>{html.escape(row['mem_pct'])}</td></tr>"
        for row in rows
    )

    chart_data = {
        "labels": times,
        "cpu": cpu_values,
        "mem": mem_values,
    }

    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>{html.escape(title)}</title>
    <script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 1.5rem; }}
        h1, h2 {{ margin-bottom: 0.2rem; }}
        table {{ border-collapse: collapse; margin-top: 1rem; width: 100%; max-width: 640px; }}
        th, td {{ border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: right; }}
        th {{ background: #f3f3f3; }}
        pre {{ background: #f8f8f8; padding: 1rem; overflow: auto; }}
        .chart-container {{ max-width: 960px; }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <p>{'All PIDs' if pid is None else f'PID {pid}'} sampled every {interval}s for {count} cycles.</p>

    <div class=\"chart-container\"> <canvas id=\"cpuChart\"></canvas> </div>
    <div class=\"chart-container\"> <canvas id=\"memChart\"></canvas> </div>

    <h2>Samples</h2>
    <table aria-label=\"pidstat samples\">
        <thead>
            <tr><th scope=\"col\">Time</th><th scope=\"col\">PID</th><th scope=\"col\">CPU %</th><th scope=\"col\">Memory %</th></tr>
        </thead>
        <tbody>
            {row_cells}
        </tbody>
    </table>

    <h2>pidstat output</h2>
    <pre>{escaped_raw_output}</pre>

    <script>
        const data = {json.dumps(chart_data)};
        const cpuCtx = document.getElementById('cpuChart');
        new Chart(cpuCtx, {{
            type: 'line',
            data: {{
                labels: data.labels,
                datasets: [{{
                    label: 'CPU %',
                    data: data.cpu,
                    fill: false,
                    borderColor: '#2563eb',
                    tension: 0.2
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ position: 'top' }}
                }},
                scales: {{
                    y: {{ beginAtZero: true, title: {{ display: true, text: 'CPU %' }} }},
                    x: {{ title: {{ display: true, text: 'Time' }} }}
                }}
            }}
        }});

        const memCtx = document.getElementById('memChart');
        new Chart(memCtx, {{
            type: 'line',
            data: {{
                labels: data.labels,
                datasets: [{{
                    label: 'Memory %',
                    data: data.mem,
                    fill: false,
                    borderColor: '#16a34a',
                    tension: 0.2
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ position: 'top' }}
                }},
                scales: {{
                    y: {{ beginAtZero: true, title: {{ display: true, text: 'Memory %' }} }},
                    x: {{ title: {{ display: true, text: 'Time' }} }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""


def write_report(html_content: str, output_path: Path) -> None:
    output_path.write_text(html_content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run pidstat and generate an HTML report with basic CPU and memory"
            " plots. If no PID is provided, pidstat monitors all processes."
        )
    )
    parser.add_argument("--pid", type=int, help="PID to profile (all if omitted)")
    parser.add_argument(
        "--interval", type=int, default=1, help="Sampling interval in seconds"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of samples to collect (per pidstat count argument)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("pidstat_report.html"),
        help="Where to write the HTML report",
    )
    parser.add_argument(
        "--title",
        default="pidstat performance report",
        help="Title shown in the HTML report",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pidstat_output = run_pidstat(args.pid, args.interval, args.count)
    rows = parse_pidstat_output(pidstat_output)
    if not rows:
        raise SystemExit("No pidstat rows parsed; check PID and pidstat output")
    html_report = build_html(
        rows,
        pidstat_output,
        pid=args.pid,
        interval=args.interval,
        count=args.count,
        title=args.title,
    )
    write_report(html_report, args.output)
    print(f"Report written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
