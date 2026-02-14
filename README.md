
# Waterquality — MitDrikkevand → MQTT → Home Assistant

Scraper public drikkevandsdata fra **MitDrikkevand.dk** for et valgt vandværk og publicerer de seneste værdier som **én retained JSON** til en MQTT broker (fx Mosquitto). Home Assistant kan derefter lave sensorer ud fra JSON’en.

> Bruges i praksis til at følge fx **Nitrat (NO3)**, **Ammonium (NH4)** og **Nitrit (NO2)** over tid.

---

## Indhold

- [Waterquality — MitDrikkevand → MQTT → Home Assistant](#waterquality--mitdrikkevand--mqtt--home-assistant)
  - [Indhold](#indhold)
  - [Hvordan det virker](#hvordan-det-virker)
  - [MQTT payload](#mqtt-payload)
  - [Konfiguration](#konfiguration)
  - [Environment variables](#environment-variables)
- [Kør lokalt](#kør-lokalt)
- [Container image](#container-image)
    - [Multi-arch (vigtigt)](#multi-arch-vigtigt)
  - [k3s / Kubernetes](#k3s--kubernetes)
  - [Home Assistant](#home-assistant)
  - [Troubleshooting](#troubleshooting)

---

## Hvordan det virker

1. Henter HTML fra en vandværks-side på MitDrikkevand.dk
2. Finder udvalgte parametre (værdi, enhed, måledato)
3. Publicerer en retained JSON på MQTT-topic

CronJob i k3s kører periodisk (fx ugentligt), stopper igen og efterlader en frisk retained state i MQTT.

---

## MQTT payload

Topic (eksempel):
```json
{
  "updated_at": "2026-02-13T20:36:45+00:00",
  "source": "https://mitdrikkevand.dk/waterplants/49809",
  "values": {
    "Nitrat (NO3)": {"value": "1,30", "unit": "mg/l", "date": "07/10 2025"},
    "Ammonium (NH4)": {"value": "< 0,005", "unit": "mg/l", "date": "07/10 2025"},
    "Nitrit (NO2)": {"value": "0,002", "unit": "mg/l", "date": "07/10 2025"}
  }
}
```

Bemærk:
	•	decimalkomma ("1,30")
	•	værdier kan være "< 0,005"

Home Assistant templates nedenfor håndterer dette.


## Konfiguration

Skift til et andet vandværk (MitDrikkevand)

Det eneste du skal ændre er:
	•	WATERPLANT_URL → URL til det ønskede vandværk på MitDrikkevand.dk
Eksempel: https://mitdrikkevand.dk/waterplants/<ID>
	•	(valgfrit) MQTT_TOPIC → nyt topic-navn, hvis du vil have flere vandværker side om side

Find vandværkets URL:
	1.	Gå til MitDrikkevand.dk
	2.	Find vandværket og kopier linket til siden (typisk /waterplants/<id>)

## Environment variables

| Variabel       | Beskrivelse                  | Eksempel                                   |
| :--------------| :--------------------------- | :----------------------------------------- |
| WATERPLANT_URL | MitDrikkevand waterplant URL | https://mitdrikkevand.dk/waterplants/49809 |
| MQTT_HOST      | Mosquitto host/IP            | ex. 192.168.1.111                          |
| MQTT_PORT      | Mosquitto port               | 1883                                       |
| MQTT_TOPIC.    | Topic til retained state.    | waterquality/frederiksberg_soroe/state.    |
| MQTT_USERNAME. | MQTT username.               | youruser                                   |
| MQTT_PASSWORD. | MQTT password                | "your#password"                            |
| MQTT_RETAIN.   | Retain message               | true                                       |
| MQTT_QOS       | QoS                          | 1                                          |


# Kør lokalt

1) venv + install
   
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) .env (commit ikke denne fil)

Opret .env i projektmappen:

```env
WATERPLANT_URL=https://mitdrikkevand.dk/waterplants/49809
MQTT_HOST=192.168.1.213
MQTT_PORT=1883
MQTT_TOPIC=waterquality/frederiksberg_soroe/state
MQTT_RETAIN=true
MQTT_QOS=1
MQTT_USERNAME=youruser
MQTT_PASSWORD="your#password"
```

Password med # skal i quotes.

3) Run
```bash
python scraper.py
```

# Container image

### Multi-arch (vigtigt)

Hvis du bygger på Apple Silicon (arm64) men dine k3s noder er amd64, skal du bygge multi-arch.
Ellers får du:
exec /usr/local/bin/python: exec format error

* Build & push (GHCR eksempel) 
```bash  
docker buildx create --use --name multiarchbuilder 2>/dev/null || docker buildx use multiarchbuilder
docker buildx inspect --bootstrap

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/<user>/waterquality-scraper:0.1.0 \
  --push . 
```
## k3s / Kubernetes

Workload er et CronJob: den kører kort og ender normalt som Completed.

**Namespace**
```bash
kubectl create namespace waterquality --dry-run=client -o yaml | kubectl apply -f -
```
**MQTT secret**

```bash
kubectl -n waterquality create secret generic waterquality-mqtt \
  --from-literal=MQTT_USERNAME='youruser' \
  --from-literal=MQTT_PASSWORD='your#password' \
  --dry-run=client -o yaml | kubectl apply -f -
```
**GHCR pull secret (kun hvis image er private)**

Token skal have read:packages.

```bash
kubectl -n waterquality create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=<github_user> \
  --docker-password='<TOKEN>' \
  --docker-email='x@example.com'
  ```
**ServiceAccount der bruger pull secret:**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: waterquality-sa
  namespace: waterquality
imagePullSecrets:
  - name: ghcr-pull-secret
```
**CronJob (eksempel)**

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: waterquality-scrape
  namespace: waterquality
spec:
  schedule: "12 6 * * 1"   # mandag 06:12
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: Never
          serviceAccountName: waterquality-sa
          containers:
            - name: scraper
              image: ghcr.io/<user>/waterquality-scraper:0.1.0
              imagePullPolicy: IfNotPresent
              env:
                - name: WATERPLANT_URL
                  value: "https://mitdrikkevand.dk/waterplants/49809"
                - name: MQTT_HOST
                  value: "192.168.1.213"
                - name: MQTT_PORT
                  value: "1883"
                - name: MQTT_TOPIC
                  value: "waterquality/frederiksberg_soroe/state"
                - name: MQTT_RETAIN
                  value: "true"
                - name: MQTT_QOS
                  value: "1"
                - name: MQTT_USERNAME
                  valueFrom:
                    secretKeyRef:
                      name: waterquality-mqtt
                      key: MQTT_USERNAME
                - name: MQTT_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: waterquality-mqtt
                      key: MQTT_PASSWORD

```
**Kør en manuel test**
```bash
kubectl -n waterquality create job --from=cronjob/waterquality-scrape waterquality-scrape-manual
kubectl -n waterquality logs -l job-name=waterquality-scrape-manual --tail=200
```
## Home Assistant

Scraperen publicerer én JSON. I nogle HA setups er value_json ikke tilgængelig i MQTT templates, derfor parses JSON med value | from_json.

Lav fx packages/waterquality.yaml:
```yaml
mqtt:
  sensor:
    - name: "Vandkvalitet Nitrat"
      state_topic: "waterquality/frederiksberg_soroe/state"
      unit_of_measurement: "mg/L"
      state_class: measurement
      icon: mdi:water-check
      value_template: >
        {% set j = value | from_json %}
        {% set v = j['values']['Nitrat (NO3)']['value'] | string %}
        {{ v | replace(',', '.') | float }}

    - name: "Vandkvalitet Ammonium"
      state_topic: "waterquality/frederiksberg_soroe/state"
      unit_of_measurement: "mg/L"
      state_class: measurement
      icon: mdi:water-check
      value_template: >
        {% set j = value | from_json %}
        {% set v = j['values']['Ammonium (NH4)']['value'] | string %}
        {% set n = v | replace('<','') | replace(',','.') | trim %}
        {{ n | float }}

    - name: "Vandkvalitet Nitrit"
      state_topic: "waterquality/frederiksberg_soroe/state"
      unit_of_measurement: "mg/L"
      state_class: measurement
      icon: mdi:water-check
      value_template: >
        {% set j = value | from_json %}
        {% set v = j['values']['Nitrit (NO2)']['value'] | string %}
        {{ v | replace(',', '.') | float }}

    - name: "Vandkvalitet Måledato Nitrat"
      state_topic: "waterquality/frederiksberg_soroe/state"
      device_class: date
      icon: mdi:calendar
      value_template: >
        {% set j = value | from_json %}
        {% set d = j['values']['Nitrat (NO3)']['date'] | string %}
        {% set parts = d.split(' ') %}
        {% set dm = parts[0].split('/') %}
        {{ parts[1] ~ '-' ~ dm[1] ~ '-' ~ dm[0] }}

    - name: "Vandkvalitet Opdateret"
      state_topic: "waterquality/frederiksberg_soroe/state"
      icon: mdi:clock
      value_template: >
        {% set j = value | from_json %}
        {% set dt = as_datetime(j['updated_at']) %}
        {{ as_local(dt).strftime('%d-%m-%Y %H:%M') }}
```

Genstart Home Assistant efter ændringer i packages.   

## Troubleshooting

**Pod ends with exec format error**

Du har bygget image til forkert CPU-arkitektur.
Byg multi-arch: linux/amd64,linux/arm64.

**HA sensorer = unknown**
    
    -   Tjek HA MQTT integration peger på samme broker som din MQTT Explorer
    -	Brug value | from_json (ikke value_json) i templates
    -	Lyt på topic i HA: waterquality/frederiksberg_soroe/state

**GHCR pull errors**
    
    -	Private images kræver imagePullSecret med token read:packages
    -	Push kræver token write:packages



