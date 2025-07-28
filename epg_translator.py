import os
import requests
import openai
from pathlib import Path
from xml.etree import ElementTree as ET
from langdetect import detect
from deep_translator import GoogleTranslator,ChatGptTranslator
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Tuple
import time


# ====== CONFIG ======
URL_LIST_FILE = 'epg_urls.txt' #URLs for full epg files to be translated. If a URL is in both URL_LIST_FILE and URL_FILTER_FILE, the filtered version prevails
LOCAL_PATHS_FILE = 'local_epg_paths.txt' #Local paths for full epg files to be translated. If a path is in both LOCAL_PATHS_FILE and LOCAL_FILTER_FILE, the filtered version prevails
URL_FILTER_FILE = 'url_channel_filters.txt' #URLs for epg files to be translated, filtered on specific channels
LOCAL_FILTER_FILE = 'local_channel_filters.txt' #Local paths for epg files to be translated, filtered on specific channels
OUTPUT_FOLDER = 'translated_epg_xmls'
SKIP_LANGUAGES = {'en', 'fr', 'es', 'it'} #skip languages for which you do not need a translation
NUM_WORKERS = 1
OPENAI_KEY = '' #only needed if you use chatgpt fallback
ENABLE_CHATGPT_FALLBACK = False
BATCH_SIZE = 500
BATCH_SIZE_CHATGPT = 50
TARGET_LANGUAGE = 'en'


# ====================

def download_xml(url):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] Failed to download {url}: {e}")
        return None

def read_local_xml(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"[ERROR] Failed to read local file {path}: {e}")
        return None

from deep_translator import GoogleTranslator, ChatGptTranslator

def translate_text(text):
    if not text.strip():
        return text

    try:
        lang = detect(text)
        if lang in SKIP_LANGUAGES:
            return text

        # First attempt: Google Translate
        try:
            google_translated = GoogleTranslator(source='auto', target=TARGET_LANGUAGE).translate(text)
        except Exception as ge:
            print(f"❌ Google translation error: \"{text}\" — {ge}")
            google_translated = text  # fallback logic will handle

        if google_translated and google_translated != text:
            return google_translated
        #else:
        #    print(f"⚠️ Google translation unchanged: \"{text}\"")

        # Fallback: ChatGPT
        if ENABLE_CHATGPT_FALLBACK:
            try:
                chatgpt_translated = ChatGptTranslator(api_key=OPENAI_KEY, target=TARGET_LANGUAGE).translate(text)
                if chatgpt_translated == text:
                    print(f"⚠️ ChatGPT translation unchanged: \"{text}\"")
                #else:
                #    print(f"⚠️ ChatGPT translation used: \"{chatgpt_translated}\"")
                return chatgpt_translated
            except Exception as ce:
                print(f"❌ ChatGPT translation error: \"{text}\" — {ce}")

        return text  # fallback: original if both fail

    except Exception as e:
        print(f"❌ Language detection or other error for: \"{text}\" — {e}")
        return text




def translate_element_text(elem, parent_tag):
    translatable_tags = {
        'channel': {'display-name'},
        'programme': {'title', 'desc', 'category', 'country'}
    }

    if elem.tag in translatable_tags.get(parent_tag, set()) and elem.text:
        original = elem.text
        translated = translate_text(original)
        if translated and translated != original:
            formatted = f"{translated} / {original}"
            return (elem, formatted)
    return (elem, None)




def get_filename_from_url(url):
    parsed = urlparse(url)
    return os.path.basename(parsed.path) or f"epg_unknown.xml"

def get_filename_from_path(path):
    return os.path.basename(path) or "local_epg.xml"

def load_channel_filters(filepath, header_key):
    """
    Parses a filter file like:
        URL http://example.com/file.xml
        Channel1
        Channel2

    - Lines starting with '#' are ignored unless it's a commented header.
    - If a header line (e.g. #URL ...) is commented, the whole block is skipped and logged.
    """
    from collections import defaultdict
    filters = defaultdict(set)
    fallback_settings = {}
    current_key = None
    skip_block = False
    force_fallback = None

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith(f"#{header_key}"):
                print(f"⏭️ Skipped commented {header_key.lower()}: {stripped}")
                current_key = None
                skip_block = True
                continue

            if stripped.startswith('#'):
                continue

            if stripped.startswith(header_key + 'NF'):
                current_key = stripped[len(header_key + 'NF'):].strip()
                skip_block = False
                fallback_settings[current_key] = False

            elif stripped.startswith(header_key + 'F'):
                current_key = stripped[len(header_key + 'F'):].strip()
                skip_block = False
                fallback_settings[current_key] = True

            elif stripped.startswith(header_key):
                current_key = stripped[len(header_key):].strip()
                skip_block = False
                fallback_settings[current_key] = None


            elif current_key and not skip_block:
                filters[current_key].add(stripped)

    return filters, fallback_settings

def should_use_chatgpt_fallback(source_key, fallback_settings):
    normalized_key = source_key.strip().lower()
    if normalized_key in fallback_settings:
        return fallback_settings[normalized_key]
    return ENABLE_CHATGPT_FALLBACK


def translate_xml_content(xml_string, allowed_channel_ids=None, log_source_name="", fallback_settings=None):
    try:
        root = ET.fromstring(xml_string)
        now = datetime.utcnow()
        three_days_later = now + timedelta(days=2)
        use_fallback = should_use_chatgpt_fallback(log_source_name, fallback_settings or {})
        print(f"🤖 ChatGPT fallback for {log_source_name}: {'ENABLED' if use_fallback else 'DISABLED'}")


        found_channel_ids = set(elem.attrib.get('id') for elem in root.findall('channel'))
        found_programme_channels = set(elem.attrib.get('channel') for elem in root.findall('programme'))
        all_present_ids = found_channel_ids.union(found_programme_channels)

        if allowed_channel_ids is not None:
            matched = allowed_channel_ids.intersection(all_present_ids)
            missing = allowed_channel_ids.difference(all_present_ids)

            if not matched:
                print(f"⚠️ WARNING: None of the specified channels were found in: {log_source_name}")
            else:
                print(f"📋 Found channels to translate in {log_source_name}: {sorted(matched)}")

            if missing:
                print(f"❌ Channels not found in {log_source_name}: {sorted(missing)}")

        # Filter <programme> based on channel and date
        for programme in list(root.findall('programme')):
            channel_ok = (
                allowed_channel_ids is None or
                programme.attrib.get('channel') in allowed_channel_ids
            )

            start_str = programme.attrib.get('start', '')[:14]
            try:
                start_time = datetime.strptime(start_str, "%Y%m%d%H%M%S")
            except ValueError:
                start_time = None
                
            stop_str = programme.attrib.get('stop', '')[:14]
            try:
                stop_time = datetime.strptime(stop_str, "%Y%m%d%H%M%S")
            except ValueError:
                stop_time = None

            # Remove if: wrong channel OR invalid date OR in the past OR beyond 3 days
            if (not channel_ok or not stop_time or stop_time <= now or stop_time > three_days_later):
                root.remove(programme)

        # Filter <channel> by id if needed
        if allowed_channel_ids is not None:
            for channel in list(root.findall('channel')):
                if channel.attrib.get('id') not in allowed_channel_ids:
                    root.remove(channel)

                # Collect only whitelisted elements to translate
        elements = []
        translatable_tags = {
            'channel': {'display-name'},
            'programme': {'title', 'desc', 'category', 'country'}
        }

        for parent in root.iter():
            parent_tag = parent.tag
            for child in list(parent):
                if child.tag not in translatable_tags.get(parent_tag, set()):
                    continue  # Skip non-whitelisted fields

                if parent_tag == "programme":
                    start_str = parent.attrib.get('start', '')[:14]
                    try:
                        start_time = datetime.strptime(start_str, "%Y%m%d%H%M%S")
                        if start_time > three_days_later:
                            continue  # skip translation
                    except ValueError:
                        continue

                elements.append((child, parent_tag))


        total = len(elements)
        print(f"🌍 Translating only whitelisted fields with {NUM_WORKERS} workers...")

        translated_pairs = batch_translate_with_fallback(elements, use_fallback)

        for i, (elem, new_text) in enumerate(translated_pairs, 1):
            if new_text and new_text.strip() != (elem.text or "").strip():
                elem.text = new_text
            if i % max(1, total // 100) == 0 or i == total:
                pct = round((i / total) * 100, 1)
                print(f"    - {pct}% complete ({i}/{total})")


        return ET.tostring(root, encoding='utf-8').decode('utf-8')

    except Exception as e:
        print(f"[ERROR] Failed to process XML: {e}")
        return xml_string

def batch_translate_worker(batch, batch_index, total_batches, use_chatgpt_fallback):
    results = [None] * len(batch)
    fallback_queue = []
    texts = [elem.text.strip() if elem.text else "" for elem, _ in batch]
    print(f"📦 Starting Google batch {batch_index}/{total_batches} with {len(batch)} items")

    try:
        translated_texts = GoogleTranslator(source='auto', target='en').translate_batch(texts)
        print(f"✅ Google batch {batch_index} succeeded.")
    except Exception as e:
        print(f"[ERROR] ❌ Google batch {batch_index} failed: {e}")
        translated_texts = [None] * len(texts)

    for j, ((elem, parent_tag), original_text, translated) in enumerate(zip(batch, texts, translated_texts)):
         # Skip empty original text
        if not original_text.strip():
            results[j] = (elem, original_text)  # keep as is
            continue
            
        if not translated:
            print(f"[WARN] Google returned None for text: \"{original_text}\"")

        if not translated or translated.strip() == original_text.strip():
            fallback_queue.append((j, original_text, (elem, parent_tag)))
        else:
            formatted = f"{translated} / {original_text}"
            results[j] = (elem, formatted)

    if fallback_queue:
        print(f"💡 {len(fallback_queue)} items queued for ChatGPT fallback after Google batch {batch_index}")
        flush_fallback_queue(fallback_queue, results, use_chatgpt_fallback)


    print(f"🏁 Finished batch {batch_index}/{total_batches}")
    return results




def batch_translate_with_fallback(elements: List[Tuple[ET.Element, str]], use_chatgpt_fallback: bool) -> List[Tuple[ET.Element, str]]:
    results = []
    total = len(elements)
    batches = [elements[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    total_batches = len(batches)

    print(f"🔄 Starting parallel batch translation: {total} elements in {total_batches} batches with {NUM_WORKERS} workers...")

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        future_to_index = {
            executor.submit(batch_translate_worker, batch, idx + 1, total_batches, use_chatgpt_fallback)
            for idx, batch in enumerate(batches)
        }

        for i, future in enumerate(as_completed(future_to_index), 1):
            try:
                batch_result = future.result()
                results.extend(batch_result)
            except Exception as e:
                print(f"[ERROR] ❌ Batch {future_to_index[future]+1} failed in thread pool: {e}")

            pct = round((i / total_batches) * 100, 1)
            print(f"   📊 {pct}% of batches completed ({i}/{total_batches})")

    print("✅ All parallel batches completed.")
    return results

def batch_translate_with_chatgpt(texts: List[str], max_retries: int = 5) -> List[str]:
    all_results = []

    for i in range(0, len(texts), BATCH_SIZE_CHATGPT):
        batch = texts[i:i+BATCH_SIZE_CHATGPT]
        attempt = 0
        while attempt < max_retries:
            try:
                attempt += 1
                print(f"🧠 ChatGPT batch translation attempt {attempt}/{max_retries} (batch {i//BATCH_SIZE_CHATGPT + 1})")
                translator = ChatGptTranslator(api_key=OPENAI_KEY, target='en')
                translated = translator.translate_batch(batch)
                all_results.extend(translated)
                break  # success, go to next batch
            except Exception as e:
                print(f"[ERROR] ❌ ChatGPT batch translation failed (attempt {attempt}/{max_retries}): {e}")
                if attempt >= max_retries:
                    print("    ⛔ Max retries reached for this batch. Returning empty results.")
                    all_results.extend([""] * len(batch))
                    break
                time.sleep(2 * attempt)  # exponential backoff

    return all_results

            
def flush_fallback_queue(fallback_queue, results_list, use_chatgpt_fallback):
    if not use_chatgpt_fallback:
        print("⚠️ ChatGPT fallback is disabled. Using original text.")
        for idx, original_text, (elem, _) in fallback_queue:
            results_list[idx] = (elem, f"{original_text} / {original_text}")
        fallback_queue.clear()
        return

    try:
        indices, texts, elem_pairs = zip(*fallback_queue)
        print(f"🧠 ChatGPT fallback processing {len(texts)} items...")
        translations = batch_translate_with_chatgpt(list(texts), max_retries=5)

        for i, (idx, translated, (elem, _)) in enumerate(zip(indices, translations, elem_pairs)):
            original_text = texts[i]
            if translated and translated != original_text.strip():
                formatted = f"{translated} / {original_text}"
                results_list[idx] = (elem, formatted)
            else:
                results_list[idx] = (elem, None)
    except Exception as e:
        print(f"[ERROR] Failed ChatGPT fallback batch: {e}")
        for idx, (_, _, (elem, _)) in enumerate(fallback_queue):
            results_list[idx] = (elem, None)
    finally:
        fallback_queue.clear()




    
def main():
    Path(OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)

    # Load filters
    url_filters, url_fallback_settings = load_channel_filters(URL_FILTER_FILE, "URL") if os.path.exists(URL_FILTER_FILE) else ({}, {})
    local_filters, local_fallback_settings = load_channel_filters(LOCAL_FILTER_FILE, "PATH") if os.path.exists(LOCAL_FILTER_FILE) else ({}, {})


    # --- Load and filter URL list ---
    urls = []
    if os.path.exists(URL_LIST_FILE):
        with open(URL_LIST_FILE, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]


    # Handle conflicts: Filtered URLs take precedence
    url_conflicts = set(urls).intersection(url_filters.keys())
    for conflict in url_conflicts:
        print(f"⚠️ URL conflict: {conflict} is listed in both {URL_LIST_FILE} and {URL_FILTER_FILE}. Filtered version will be used.")
    urls_to_translate = [u for u in urls if u not in url_filters]

    # --- Process filtered URLs ---
    for i, (url, allowed_channels) in enumerate(url_filters.items(), start=1):
        print(f"\n🎯 [Filtered URL {i}/{len(url_filters)}] Downloading: {url}")
        xml_data = download_xml(url)
        if not xml_data:
            continue

        translated_xml = translate_xml_content(xml_data, allowed_channel_ids=allowed_channels, log_source_name=url, fallback_settings=url_fallback_settings)
        filename = get_filename_from_url(url)
        out_path = Path(OUTPUT_FOLDER) / filename
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(translated_xml)
        print(f"✅ Saved translated XML to: {out_path}")

    # --- Process unfiltered URLs (full translation) ---
    for i, url in enumerate(urls_to_translate, start=1):
        print(f"\n📥 [URL {i}/{len(urls_to_translate)}] Downloading: {url}")
        xml_data = download_xml(url)
        if not xml_data:
            continue

        translated_xml = translate_xml_content(xml_data, allowed_channel_ids=None, log_source_name=url, fallback_settings=url_fallback_settings)
        filename = get_filename_from_url(url)
        out_path = Path(OUTPUT_FOLDER) / filename
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(translated_xml)
        print(f"✅ Saved translated XML to: {out_path}")

    # --- Load and filter local paths ---
    paths = []
    if os.path.exists(LOCAL_PATHS_FILE):
        with open(LOCAL_PATHS_FILE, 'r', encoding='utf-8') as f:
            paths = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]


    # Handle conflicts: Filtered PATHs take precedence
    local_conflicts = set(paths).intersection(local_filters.keys())
    for conflict in local_conflicts:
        print(f"⚠️ PATH conflict: {conflict} is listed in both {LOCAL_PATHS_FILE} and {LOCAL_FILTER_FILE}. Filtered version will be used.")
    paths_to_translate = [p for p in paths if p not in local_filters]

    # --- Process filtered local files ---
    for i, (path, allowed_channels) in enumerate(local_filters.items(), start=1):
        print(f"\n🎯 [Filtered PATH {i}/{len(local_filters)}] Reading: {path}")
        xml_data = read_local_xml(path)
        if not xml_data:
            continue

        translated_xml = translate_xml_content(xml_data, allowed_channel_ids=allowed_channels, log_source_name=path, fallback_settings=local_fallback_settings)
        filename = get_filename_from_path(path)
        out_path = Path(OUTPUT_FOLDER) / filename
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(translated_xml)
        print(f"✅ Saved translated XML to: {out_path}")

    # --- Process unfiltered local files (full translation) ---
    for i, path in enumerate(paths_to_translate, start=1):
        print(f"\n📂 [Local {i}/{len(paths_to_translate)}] Reading: {path}")
        xml_data = read_local_xml(path)
        if not xml_data:
            continue

        translated_xml = translate_xml_content(xml_data, allowed_channel_ids=None, log_source_name=path, fallback_settings=local_fallback_settings)
        filename = get_filename_from_path(path)
        out_path = Path(OUTPUT_FOLDER) / filename
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(translated_xml)
        print(f"✅ Saved translated XML to: {out_path}")


if __name__ == '__main__':
    main()
