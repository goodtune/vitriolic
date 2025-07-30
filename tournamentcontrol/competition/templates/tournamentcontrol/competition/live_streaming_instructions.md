# Live Streaming

## {{ competition.title }} {{ season.title }}

Please find the technical details for connecting the live stream of this tournament to the FIT streaming accounts.

## 1. Platforms

- **YouTube** – https://youtube.com/internationaltouch  
- **Facebook** – https://www.facebook.com/internationaltouch.org  
- **LinkedIn** – https://www.linkedin.com/company/internationaltouch  
- **Twitter** – https://twitter.com/intltouchorg  

## 2. Providers

### 2.1 Production

We will be using **``PLACEHOLDER``** to produce the programme feed.

1. Field ``PLACEHOLDER`` **with** commentary (remote)  
2. ``PLACEHOLDER``

### 2.2 Distribution via restream.io

The primary feed is pushed to **restream.io**, which simul‑casts to the platforms in *Section&nbsp;1*.

| Item | Value |
|------|-------|
| Login URL | https://app.restream.io/home |
| Account (Google SSO) | scores@tournaments.fit |
| RTMP endpoint | rtmp://live.restream.io/live |
| Stream key | ``PLACEHOLDER`` |

1. Sign in as a **co-host**.  
2. Confirm the programme feed is being received.  
3. Toggle downstream platforms **on/off** as required.

If restream fails and ``PLACEHOLDER`` is unreachable, switch to the emergency keys in *Section&nbsp;3*.

## 3. Technical Details

### 3.1 Primary Uplink

| Description | RTMP Endpoint | Stream Key |
|-------------|---------------|-----------|
| Primary feed (Field ``PLACEHOLDER``) | ``PLACEHOLDER`` | ``PLACEHOLDER`` |

### 3.2 Emergency / Direct-to-Platform Keys

| Platform | RTMP Endpoint | Stream Key | Notes |
|----------|---------------|-----------|-------|
| YouTube | rtmp://a.rtmp.youtube.com/live2 | {% if ground.stream_key %}{{ ground.stream_key }}{% else %}``PLACEHOLDER``{% endif %} | Use if restream unavailable |
| Facebook | rtmps://live-api-s.facebook.com:443/rtmp/ | ``PLACEHOLDER`` | — |

## 4. Google Workspace Account

| Item | Value |
|------|-------|
| Start URL | https://workspace.google.com/dashboard |
| Account | scores@tournaments.fit |
| Password | ``PLACEHOLDER`` |

Use this shared account to access the FIT dashboard and live‑stream controls.

## 5. Operating the FIT Stream Controller

1. **Sign in** at https://workspace.google.com/dashboard and launch the "FIT" app.  
2. Open:  
   - Runsheet → <a href="{% url 'competition:runsheet' competition.slug season.slug %}">Runsheet</a>  
   - Results → <a href="{% url 'competition:results' competition.slug season.slug %}">Results</a>  
   - Stream  → <a href="{% url 'competition:stream' competition.slug season.slug %}">Stream</a>
3. On the *Stream* page, choose the upcoming match and press **Start streaming** ~1 min before tap‑off.  
4. After full‑time, press **Stop streaming**. Repeat for every match.

## 6. Roles & Responsibilities

| Role | Morning Setup | During Play | Evening Shutdown |
|------|---------------|-------------|------------------|
| ``PLACEHOLDER`` | Confirm production feed is received; start outputs in restream.io | On‑call for issues | Reset outputs to *Off* |
| Restream operator | Activate restream outputs; verify downstream platforms | Monitor health | Turn all outputs *Off* |
| Commentator – Field ``PLACEHOLDER`` | — | Start/stop each match stream in FIT controller | — |

## 7. Scores Graphic Control *(if applicable)*

- Field ``PLACEHOLDER`` scores are driven by the commentator laptop.  
- For multi-field events, graphics operators are listed in *Section 6*.

## 8. Contact

- Technical lead: **``PLACEHOLDER``** 〈``PLACEHOLDER``〉  
- Event manager: **``PLACEHOLDER``** 〈``PLACEHOLDER``〉

*Template version: 2025‑07‑30.*