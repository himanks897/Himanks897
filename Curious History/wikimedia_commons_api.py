import requests

HEADERS = {"User-Agent": "CuriousHistory/1.0 (dev@curioushistory.app)"}
BASE    = "https://commons.wikimedia.org/w/api.php"

def get_image_info(file_title):
    try:
        r = requests.get(BASE, headers=HEADERS, params={
            "action": "query", "titles": file_title,
            "prop": "imageinfo", "iiprop": "url|extmetadata|dimensions",
            "iiurlwidth": 600, "format": "json"
        }, timeout=10)
        r.raise_for_status()
        pages = r.json()["query"]["pages"]
        page  = next(iter(pages.values()))
        info  = page.get("imageinfo", [{}])[0]
        meta  = info.get("extmetadata", {})
        url   = info.get("thumburl") or info.get("url","")
        if not url: return None
        return {
            "title":       file_title.replace("File:", ""),
            "url":         url,
            "full_url":    info.get("url",""),
            "license":     meta.get("LicenseShortName",{}).get("value",""),
            "description": meta.get("ImageDescription",{}).get("value","")[:200],
            "artist":      meta.get("Artist",{}).get("value",""),
            "source":      "Wikimedia Commons"
        }
    except Exception:
        return None

def search_images(query, limit=10):
    try:
        r = requests.get(BASE, headers=HEADERS, params={
            "action": "query", "list": "search",
            "srsearch": f"{query} filetype:bitmap",
            "srnamespace": 6, "srlimit": limit, "format": "json"
        }, timeout=10)
        r.raise_for_status()
        results = r.json().get("query", {}).get("search", [])
        images  = []
        for item in results[:8]:
            info = get_image_info(item.get("title",""))
            if info: images.append(info)
        return images
    except Exception:
        return []

def get_category_images(category, limit=10):
    try:
        r = requests.get(BASE, headers=HEADERS, params={
            "action": "query", "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmtype": "file", "cmlimit": limit, "format": "json"
        }, timeout=10)
        r.raise_for_status()
        members = r.json()["query"]["categorymembers"]
        images  = []
        for m in members[:8]:
            info = get_image_info(m.get("title",""))
            if info: images.append(info)
        return images
    except Exception:
        return []
