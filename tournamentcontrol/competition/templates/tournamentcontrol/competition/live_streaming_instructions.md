# Live Streaming

## {{ competition.title }} {{ season.title }}

Please find the technical details for connecting the live stream of this tournament to the FIT streaming accounts.

## 1. Platforms

- **YouTube:** [internationaltouch](https://youtube.com/internationaltouch)
- **Facebook:** [internationaltouch.org](https://www.facebook.com/internationaltouch.org)
- **LinkedIn:** [internationaltouch](https://www.linkedin.com/company/internationaltouch)

## 2. Providers

### 2.1 Production

We will be using **`COMPANY NAME`** to produce the live feeds.

### 2.2 Distribution via `restream.io`

The primary feed is pushed to **restream.io**, which can re-cast to the platforms listed above.

| Item                 | Value                                       |
| -------------------- | ------------------------------------------- |
| **Login URL**        | [app.restream.io](https://app.restream.io/) |
| Account (Google SSO) | `scores@tournaments.fit`                    |

1. Sign in as a **co-host**.
2. Confirm the programme feed is being received.
3. Toggle downstream platforms **on/off** as required.

If **restream.io** fails, switch to the emergency keys listed below.

## 3. Technical Details

### 3.1 Primary Uplink

| Description            | RTMP Endpoint                  | Stream Key    |
| ---------------------- | ------------------------------ | ------------- |
| Primary feed (Field 1) | `rtmp://live.restream.io/live` | `INSERT STREAM KEY` |

### 3.2 Emergency / Direct-to-Platform Keys

| Platform | RTMP Endpoint | Stream Key | Notes |
| -------- | ------------- | ---------- | ----- |{% for ground in streaming_grounds %}
| YouTube - {{ ground.title }} | rtmp://a.rtmp.youtube.com/live2 | {{ ground.stream_key }} | {% if forloop.first %}Use if restream unavailable{% else %}-{% endif %} |{% endfor %}
| Facebook | rtmps://live-api-s.facebook.com:443/rtmp/ | `INSERT STREAM KEY` | Use if restream unavailable |

## 4. Google Workspace Account

| Item      | Value                                                                            |
| --------- | -------------------------------------------------------------------------------- |
| Start URL | [https://workspace.google.com/dashboard](https://workspace.google.com/dashboard) |
| Account   | scores@tournaments.fit                                                           |
| Password  | This will be shared via WhatsApp by the Event Manager                            |

Use this shared account to access the FIT dashboard and live‑stream controls.

## 5. Operating the FIT Stream Controller

1. **Sign in** at [https://workspace.google.com/dashboard](https://workspace.google.com/dashboard) and launch the **FIT** app.
2. Open:
   - **Runsheets:** {% url 'competition:runsheet' competition.slug season.slug as runsheet %}[{{ runsheet }}]({{ runsheet }})
   - **Results Entry:** {% url 'competition:results' competition.slug season.slug as results %}[{{ results }}]({{ results }})
   - **Stream Control:** {% url 'competition:stream' competition.slug season.slug as stream %}[{{ stream }}]({{ stream }})
3. On the _Stream_ page, choose the upcoming match and press **Start streaming** ~1 min before tap‑off.
4. After full‑time, press **Stop streaming**.
   - Repeat for every match.

## 6. Roles & Responsibilities

| Role              | Morning Setup                                                       | During Play        | Evening Shutdown       |
| ----------------- | ------------------------------------------------------------------- | ------------------ | ---------------------- |
| `PLACEHOLDER`     | Confirm production feed is received; start outputs in `restream.io` | On‑call for issues | Reset outputs to _Off_ |
| Restream operator | Activate restream outputs; verify downstream platforms              | Monitor health     | Turn all outputs _Off_ |

## 7. Contact

- **Technical lead:** `INSERT NAME`
- **Event manager:** `INSERT NAME`
