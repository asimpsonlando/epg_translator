# epg_translator
A python script to translate EPG files in XMLTV standard, using Google Translate (with fallback to ChatGPT available)

## Repository content description
- `LICENSE`: MIT License description
- `README.md`: this file
- `epg_translator.py`: the script
- `config.txt` : main configuration file
- `epg_urls.txt`, `local_channel_filters.txt`, `local_epg_paths.txt`, `url_channel_filters.txt`: configuration files containing the location of the EPG files and channel filters (when applicable)

## Description of capabilities
- This script downloads online EPG files or uses locally hosted EPG files, translates relevant fields (channel `display-name`, programme `title`, `desc`, `category` and `country`) for the next 3 days (will be configurable in the future), and returns and stores locally an output EPG file, where translated text is followed by a / sign and the original text.
- For example:
```
News / Vijesti
```
- You can then use that local output EPG file has a source EPG in your IPTV app.
- Either all the channels contained in an EPG file can be translated, or only a subset of them, defined in configuration files.
- Translation is done by batch through Google Translate (free) via the deep_translator python package. The script has the capability to fallback to ChatGPT in case the translation via Google Translate errors or returns unchanged text. Please note that ChatGPT translation is not free, and you need a ChatGPT API key for the fallback function to work. You can leave it empty and disable the fallback function if you do not want to be charged. Google Translate works fine 99% of the cases.
- Please note this has been only tested on Windows. Since there is a capability to point to local EPG files via entering their path, this might not work in other OSs. I might test it on Mac and Linux in the future.

## How to install
- Copy the contents of this repository in a local folder on your machine.
- The following python packages need to be installed for the script to run: `requests`, `langdetect`, `deep_translator` and `openai`.
  - To install these packages, use:
  ```
  pip install requests
  pip install langdetect
  pip install deep_translator
  pip install openai
  ```
  - You might need to install other packages depending on what is already installed on your machine. Refer to the import command at the start of the script to identify potentially missing packages.
## How to run script
- Script is run simply by:
```
python epg_translator.py
```
- Please note that the translation process is slow. It is recommended to schedule the script to run at night so that translated EPG files are ready in the morning.
- Translated XMLTV EPG files will be saved in the `translated_epg_xmls` folder, with the same name as the original file.
- If you want to target a different configuration file (with a name different from `config.txt`, or not in the same location), you can use the following option:
  ```
  python epg_translator.py -c new_config.txt
  ```
  or
  ```
  python epg_translator.py --config new_config.txt
  ```
- You can create a batch file starting the script and run it through Windows Task Scheduler daily. For example:
  ```
  cd C:\epg_translator
  python epg_translator.py
  ```
  
## Variables to configure inside the main configuration file (`config.txt`)
- The following variables can be configured in `config.txt`:
  - `SKIP_LANGUAGES = {'en', 'fr', 'es', 'it'}` : Skip languages for which you do not need a translation
  - `OPENAI_KEY = 'sk-xxx'` : Only needed if you are planning to use ChatGPT translation fallback (you will be charged for API usage!)
  - `ENABLE_CHATGPT_FALLBACK = False` : Can be true if you want to fallback to ChatGPT if the Google translation fails or is identical to the original text, or false to disable this fallback. Please note that this can be overridden at URL / local file path level.
  - `BATCH_SIZE = 500` : Number of translations requested at the same time in one Google Translate batch query. From my testing, 500 is a good number, but you can play with it if you want to try.
  - `BATCH_SIZE_CHATGPT = 50` : Number of translations requested at the same time in one fallback ChatGPT batch query. From my testing, 50 is a good number, but you can play with it if you want to try.
  - `TARGET_LANGUAGE = 'en'`  : Target language of the translation
- It is recommended not to modify the following variables (might be useful in the future, but not as of now)
  - `URL_LIST_FILE = 'epg_urls.txt'` : URLs for full EPG files to be translated. If a URL is in both URL_LIST_FILE and URL_FILTER_FILE, the filtered version prevails
  - `LOCAL_PATHS_FILE = 'local_epg_paths.txt'`: Local paths for full EPG files to be translated. If a path is in both LOCAL_PATHS_FILE and LOCAL_FILTER_FILE, the filtered version prevails
  - `URL_FILTER_FILE = 'url_channel_filters.txt'`: URLs for EPG files to be translated, filtered on specific channels
  - `LOCAL_FILTER_FILE = 'local_channel_filters.txt'` : Local paths for EPG files to be translated, filtered on specific channels
  - `OUTPUT_FOLDER = 'translated_epg_xmls'` : Folder in which output translated EPG files are saved
  - `NUM_WORKERS = 1`: This is the number of parallel workers handling translations. Anything higher than 1 gives unreliable results for now, so please do not change it!
## How to specify source EPG files and channels to include in output EPG file
- 4 configuration files are available
  - `epg_urls.txt` : This file contains the list of URLs for online EPGs for which all channels will be included in the output EPG (no channel selection). It is a plain text list of URLs. Fallback to ChatGPT will follow setting at script level (`ENABLE_CHATGPT_FALLBACK`) - override not possible (it will be possible in the future).
    - Example of syntax:
      ```
      https://www.open-epg.com/files/serbia1.xml
      https://www.open-epg.com/files/croatia1.xml
      ``` 
  - `local_epg_paths.txt` : This file contains the list of local paths for local EPG files for which all channels will be included in the output EPG (no channel selection). It is a plain text list of local file paths. Please note this has been tested only on Windows, with Windows file paths. Fallback to ChatGPT will follow setting at script level (`ENABLE_CHATGPT_FALLBACK`) - override not possible (it will be possible in the future).
    - Example of syntax:
      ```
      C:\epg_files\epg1.xml
      C:\epg_files\epg2.xml
      ``` 

  - `url_channel_filters.txt` : This file contains the list of URLs for online EPGs for which a selection of channels will be included in the output EPG.
    - Syntax:
      - URLs are preceded by a URL keyword
        - `URL` : URL for which fallback to ChatGPT follows the setting at script level
        - `URLF` : URL for which fallback to ChatGPT is forced (overrides the setting at script level)
        - `URLNF` : URL for which fallback to ChatGPT is force disabled (overrides the setting at script level)
        - any keyword preceded by `#` : This URL is ignored
      - Each URL line is followed by the list of channels to include in the output file. Channels are identified by their channel id in the xml file.
        - For example:
          ```
          <channel id="TVCG 1 HD.me">
          ```
          Here, the channel is identified by **TVCG 1 HD.me**
      - If a URL is in both `url_channel_filters.txt` and `epg_urls.txt`, the channel filter takes precedence.
      - Example of syntax:
        - ```
          URLNF https://www.open-epg.com/files/china1.xml
          CCTV-1 综合.cn
          CCTV-2 财经.cn
          
          URLF https://www.open-epg.com/files/serbia1.xml
          RTS 1.rs
          RTS 2.rs
          RTS 3.rs
          
          URL https://www.open-epg.com/files/serbia3.xml
          Televizija Crne Gore MNE.rs
          
          #URL https://www.open-epg.com/files/turkey3.xml
          TV8 HD.tr
          ATV HD.tr
          BEYAZ TV HD.tr
          ```

  - `local_channel_filters.txt` : This file contains the list of local file paths for local EPG files for which a selection of channels will be included in the output EPG.
    - Syntax:
      - Local file paths are preceded by a PATH keyword
        - `PATH` : Local file path for which fallback to ChatGPT follows the setting at script level
        - `PATHF` : Local file path for which fallback to ChatGPT is forced (overrides the setting at script level)
        - `PATHNF` : Local file path for which fallback to ChatGPT is force disabled (overrides the setting at script level)
        - any keyword preceded by `#` : This local file path is ignored
      - Each local file path line is followed by the list of channels to include in the output file. Channels are identified by their channel id in the xml file.
        - For example:
          ```
          <channel id="TVCG 1 HD.me">
          ```
          Here, the channel is identified by **TVCG 1 HD.me**
      - If a local file path is in both `local_channel_filters.txt` and `local_epg_paths.txt`, the channel filter takes precedence.
      - Example of syntax:
        - ```
          PATHNF C:\epg_files\testepg_nofallback.xml
          HRT 1.hr
          HRT 2.hr
          
          PATHF C:\epg_files\testepg_fallback.xml
          RTS1.rs
          RTS2.rs
          
          PATH C:\epg_files\testepg_defaultfallback.xml
          RTCG1.me
          RTCG2.me
          
          #PATH C:\epg_files\testepg_bypassed.xml
          HRT 3.hr
          ```
    
## Known issues
- The Google Translate API used by `deep_translator` does not work properly if several API calls are made in parallel. Please keep the number of worker to 1.
  
## How to use resulting xml EPG files
- Instead of pointing your IPTV app to the original XMLTV EPG file (either online or local), point it to the translated XMLTV EPG file stored in the `translated_epg_xmls` folder.
