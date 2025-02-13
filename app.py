from flask import Flask, render_template_string, request, redirect, url_for
import os
import yaml


app = Flask(__name__)


CONFIG_FILE = "/config/config.yml"

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as file:
        ALERTS = yaml.safe_load(file)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Alert Exporter</title>
    <script>
        function toggleAlert(alertKey) {
            fetch(`/${alertKey}/toggle`, { method: 'POST' });
        }
    </script>
</head>
<body>
    <h1>ADAM</h1>
    <form>
        {% for key, alert in alerts.items() %}
            <div>
                <label>
                    <input type="checkbox" name="alerts" value="{{ key }}" {% if alert.enabled %}checked{% endif %} onclick="toggleAlert('{{ key }}')">
                    {{ key }}
                </label>
            </div>
        {% endfor %}
    </form>
</body>
</html>
"""

@app.route("/<alert_key>/toggle", methods=["POST"])
def toggle_alert(alert_key):
    if alert_key in ALERTS:
        ALERTS[alert_key]["enabled"] = not ALERTS[alert_key]["enabled"]
    return "", 204

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        selected_alerts = request.form.getlist("alerts")
        for key in ALERTS:
            ALERTS[key]["enabled"] = key in selected_alerts
        return redirect(url_for("index"))

    return render_template_string(HTML_TEMPLATE, alerts=ALERTS)

@app.route("/metrics")
def metrics():
    lines = []
    for key, alert in ALERTS.items():
        if alert["enabled"]:
            value = alert.get("value")
            labels = ",".join([f"{k}=\"{v}\"" for k, v in alert["labels"].items()])
            lines.append(f"{key}{{{labels}}} {value}")
    return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain"}


if __name__ == "__main__":
    port = int(os.environ.get("ADAM_PORT", 5067))
    app.run(host="0.0.0.0", port=port)
