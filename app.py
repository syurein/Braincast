# -*- coding: utf-8 -*-
import os
import time
import random
from flask import Flask, render_template, request, jsonify
import yt_dlp
import requests # requestsライブラリをインポート
import base64
from google import genai
import google.generativeai as genai
import json
import time
import os
import re
import random
import logging
import traceback

# --- アプリケーション設定 ---
app = Flask(__name__)
# セキュリティのため、実際の運用では環境変数などから読み込むことを推奨
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))

# --- GAS Web App URL ---
# 環境変数から取得するか、直接記述（テスト用）
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# ★ 必ず実際のGAS WebアプリケーションのURLに置き換えるか、         ★
# ★ 環境変数 'GAS_WEB_APP_URL' を設定してください。             ★
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# GAS_WEB_APP_URL = 'https://script.google.com/macros/s/AKfycbzcOZSPIvKq__QQJlMH5wBgnjjiio-vgtCpNrxAYO5hE3LVIY42I0GsGFO32hwraV4g/exec' # 元のURLのまま
GAS_WEB_APP_URL = os.getenv('GAS_WEB_APP_URL', 'https://script.google.com/macros/s/AKfycbzcOZSPIvKq__QQJlMH5wBgnjjiio-vgtCpNrxAYO5hE3LVIY42I0GsGFO32hwraV4g/exec') # 環境変数から取得、なければプレースホルダ

# --- ログ設定 ---
logging.basicConfig(
    level=logging.DEBUG, # 開発中はDEBUG、本番ではINFOなどに変更
    format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
    handlers=[
        logging.StreamHandler() # コンソールに出力
        # 必要に応じてファイルハンドラを追加
        # logging.FileHandler("app.log", encoding='utf-8')
    ]
)
logging.getLogger('urllib3').setLevel(logging.WARNING) # requestsライブラリのログレベル調整
logging.getLogger('google').setLevel(logging.WARNING) # googleライブラリのログレベル調整
logging.getLogger('yt_dlp').setLevel(logging.INFO) # yt-dlpのログレベルをINFOに設定 (DEBUGだと多すぎる可能性)

# --- バックエンド処理関数 ---

def download_and_extract_audio(youtube_url):
    """
    yt-dlpを使って動画をダウンロードし、音声をMP3形式で抽出する。
    成功したら (音声ファイルパス, 動画情報) のタプルを、失敗したら (None, None) を返す。
    """
    output_dir = 'downloads'
    os.makedirs(output_dir, exist_ok=True)
    logging.debug(f"音声保存ディレクトリ: {os.path.abspath(output_dir)}")

    output_template = os.path.join(output_dir, '%(id)s.%(ext)s')

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': output_template,
        'noplaylist': True,
        'logger': logging.getLogger('yt_dlp'),
        'verbose': False,
    }

    audio_file_path = None
    info_dict_result = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logging.info(f"yt-dlp: {youtube_url} のダウンロードと音声抽出を開始")
            info_dict = ydl.extract_info(youtube_url, download=True)
            video_id = info_dict.get('id', 'unknown_id')
            # 動画情報も返すようにする
            info_dict_result = {
                'id': video_id,
                'title': info_dict.get('title', f'動画 {video_id}'),
                'thumbnail': info_dict.get('thumbnail'), # サムネイルURL
                'uploader': info_dict.get('uploader'),
                'duration': info_dict.get('duration'),
            }
            logging.info(f"yt-dlp: 動画情報取得完了 (ID: {video_id}, Title: {info_dict_result['title']})")

            base_filename = ydl.prepare_filename(info_dict)
            expected_mp3_path = os.path.splitext(base_filename)[0] + '.mp3'

            wait_time = 0
            max_wait = 10 # 少し長めに待つ (10秒)
            while not os.path.exists(expected_mp3_path) and wait_time < max_wait:
                logging.debug(f"MP3ファイル待機中: {expected_mp3_path} (待機時間: {wait_time}秒)")
                time.sleep(1)
                wait_time += 1

            if os.path.exists(expected_mp3_path):
                 audio_file_path = expected_mp3_path
                 logging.info(f"yt-dlp: 音声抽出完了 -> {audio_file_path}")
                 return audio_file_path, info_dict_result
            else:
                 logging.warning(f"期待されたMP3ファイルが見つかりません: {expected_mp3_path}")
                 potential_files = [f for f in os.listdir(output_dir) if f.startswith(video_id) and f.endswith('.mp3')]
                 if potential_files:
                     audio_file_path = os.path.join(output_dir, potential_files[0])
                     logging.info(f"yt-dlp: 代替検索で見つかった音声ファイル -> {audio_file_path}")
                     return audio_file_path, info_dict_result
                 else:
                    logging.error("yt-dlp: 音声抽出後のMP3ファイル特定に失敗しました。")
                    logging.error(f"Downloads directory contents: {os.listdir(output_dir)}")
                    return None, info_dict_result # ファイルパスはNoneだが情報は返す

    except yt_dlp.utils.DownloadError as e:
        logging.error(f"yt-dlp ダウンロードエラー: {e}")
        if "confirm your age" in str(e).lower():
             logging.error("年齢確認が必要な動画の可能性があります。クッキーファイルの使用を検討してください。")
        elif "video unavailable" in str(e).lower():
             logging.error("動画が利用不可能なようです。")
        elif "Private video" in str(e):
             logging.error("非公開動画のようです。")
        return None, None
    except Exception as e:
        logging.error("yt-dlp: 音声抽出中に予期せぬエラーが発生しました。", exc_info=True)
        return None, None

def transcribe_audio(audio_path):
    """
    Google Gemini API を使用して音声ファイルを文字起こし・要約する。
    成功した場合は、Geminiが生成したテキスト（JSON形式を期待）を返す。
    失敗した場合は None を返す。
    """
    # 環境変数名は 'GEMINI_API_KEY' を推奨 (コード内と合わせる)
    api_key = os.getenv('GEMINI') # 環境変数名を修正
    if not api_key:
        logging.error("環境変数 'GEMINI_API_KEY' が設定されていません。")
        return None

    try:
        genai.configure(api_key=api_key)
    except Exception as config_err:
         logging.error(f"Gemini API キーの設定に失敗しました: {config_err}")
         return None

    audio_file_resource = None # finally で使うため
    try:
        logging.info(f"Gemini: ファイルアップロード開始 - {audio_path}")
        # 大きなファイルの場合、タイムアウト時間を長く設定
        audio_file_resource = genai.upload_file(path=audio_path, request_options={'timeout': 600})
        logging.info(f"Gemini: ファイルアップロード完了 - Name: {audio_file_resource.name}, URI: {audio_file_resource.uri}")

        model = genai.GenerativeModel("models/gemini-1.5-pro-latest")

        # プロンプト: 文字起こし、要約、JSON形式での出力を明確に指示 (日本語版)
        prompt_parts = [
            "提供された音声ファイルに対して、以下のタスクを実行してください：",
            "1. 音声の内容を正確にテキストに文字起こししてください。",
            "2. 文字起こし結果に基づき、プレゼンテーションのスライドに適した、論理的なポイントやセクションに分けた簡潔な要約を生成してください。",
            "3. 生成された要約は、**厳密にJSONリスト形式**でフォーマットしてください。JSONリストそのもの以外には、**一切のテキスト（導入文、説明、謝罪、```jsonのようなマークダウン形式など）を含めないでください**。",
            "\n**必須のJSON構造:**",
            "出力は**必ず**有効なJSONリスト `[]` でなければなりません。",
            "リストの各要素は**必ず**以下のキーを持つJSONオブジェクト `{}` でなければなりません：",
            "  - `\"id\"`: スライド番号を表す文字列（例: \"s1\", \"s2\", \"s3\"）。",
            "  - `\"type\"`: 文字列であり、**必ず**正確に `\"summary\"` でなければなりません。",
            "  - `\"text\"`: スライドの要約テキストを含む文字列。テキスト内の改行には `\\n` を使用してください。",
            "\n**必須のJSON出力形式の例（この例自体を応答に含めないでください）：**",
            '[{"id": "s1", "type": "summary", "text": "This is the first summary point.\\nIt can span multiple lines."}, {"id": "s2", "type": "summary", "text": "This is the second summary point."}]',
            "\nそれでは、以下の音声ファイルを処理してください：",
            audio_file_resource # アップロードしたファイルリソースを渡す
        ]

        logging.info("Gemini: 文字起こし・要約生成リクエスト送信中...")
        generation_config = genai.types.GenerationConfig(
            temperature=0.5,
            # response_mime_type="application/json" # 期待通り動作しない場合があるためコメントアウト
        )
        safety_settings = [ # デフォルトより緩めに設定 (必要に応じて調整)
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ]

        response = model.generate_content(
            prompt_parts,
            generation_config=generation_config,
            safety_settings=safety_settings,
            request_options={'timeout': 600} # 生成自体のタイムアウトも設定
        )
        logging.info("Gemini: 応答受信完了")

        if not response.candidates or not response.candidates[0].content.parts:
             logging.error("Gemini: 応答に有効なコンテンツが含まれていません。")
             logging.debug(f"Gemini Full Response: {response}")
             # 安全性フィルターによるブロックの可能性を確認
             if response.prompt_feedback and response.prompt_feedback.block_reason:
                  logging.error(f"Gemini: プロンプトがブロックされました。理由: {response.prompt_feedback.block_reason}")
             if response.candidates and response.candidates[0].finish_reason != 'STOP':
                  logging.error(f"Gemini: 生成が予期せず終了しました。理由: {response.candidates[0].finish_reason}")
             return None

        generated_text = response.text.strip()
        logging.debug(f"Gemini Generated Text (raw):\n---\n{generated_text}\n---")

        # 応答からJSONを抽出する試み (```json ... ``` も考慮)
        json_str = None
        match_code_block = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', generated_text, re.IGNORECASE | re.DOTALL)
        if match_code_block:
            json_str = match_code_block.group(1).strip()
            logging.debug("Gemini: 応答から ```json ... ``` ブロックを抽出しました。")
        else:
             # コードブロックがない場合、全体がJSONか試す
             json_match = re.search(r'^\s*([\[{].*[\]}])\s*$', generated_text, re.DOTALL)
             if json_match:
                 json_str = json_match.group(1)
                 logging.debug("Gemini: 応答全体がJSON形式の可能性があります。")
             else:
                 logging.warning("Gemini: 応答が期待されるJSON形式（コードブロックまたは全体）ではありませんでした。")

        if json_str:
            try:
                parsed_json = json.loads(json_str)
                if isinstance(parsed_json, list):
                    logging.info("Gemini: 応答は期待通りのJSONリスト形式でした。")
                    output_filename = "gemini_summary_output.json"
                    try:
                        with open(output_filename, "w", encoding="utf-8") as f:
                            json.dump(parsed_json, f, ensure_ascii=False, indent=2)
                        logging.debug(f"Gemini 応答 (JSON) を {output_filename} に保存しました。")
                    except IOError as e:
                        logging.error(f"Gemini 応答のファイル保存に失敗: {e}")
                    return json_str # JSON文字列を返す
                else:
                    logging.warning("Gemini: 応答はJSONでしたが、リスト形式ではありませんでした。テキストとして扱います。")
                    # JSONだがリストでない場合も、元のテキスト全体を返す方が情報損失が少ないかも
                    # return json_str
            except json.JSONDecodeError as e:
                logging.warning(f"Gemini: 抽出したJSON文字列のパースに失敗しました: {e}。応答全体をテキストとして扱います。")
                # パース失敗した場合も、元のテキスト全体を返す

        # JSONとして処理できなかった場合、元の生成テキスト全体を返す
        logging.warning("Gemini: 応答をJSONリストとして処理できませんでした。応答テキスト全体を返します。")
        output_filename = "gemini_non_json_output.txt"
        try:
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(generated_text)
            logging.debug(f"Gemini 応答 (非JSON/エラー) を {output_filename} に保存しました。")
        except IOError as e:
            logging.error(f"Gemini 応答のファイル保存に失敗: {e}")
        return generated_text # 元のテキストをそのまま返す

    except genai.types.generation_types.BlockedPromptException as e:
        logging.error(f"Gemini: プロンプトが安全上の理由でブロックされました: {e}")
        return None
    except genai.types.generation_types.StopCandidateException as e:
         logging.error(f"Gemini: 生成が予期せず停止しました (例: 安全フィルター): {e}")
         return None
    except Exception as e:
        # google.api_core.exceptions.DeadlineExceeded などもここで捕捉
        if "DeadlineExceeded" in str(type(e)):
             logging.error(f"Gemini: API呼び出しがタイムアウトしました: {e}")
        else:
             logging.error(f"Gemini API 呼び出し中に予期せぬエラーが発生しました。", exc_info=True)
        return None
    finally:
        if audio_file_resource:
            # ファイル削除APIは非同期の場合があるため注意が必要。
            # 現状のライブラリでは delete_file は同期的に見えるが、ドキュメント確認推奨。
            # 一旦、削除処理はコメントアウトし、手動または別プロセスでの削除を検討。
            logging.warning(f"Gemini: アップロード済みファイル '{audio_file_resource.name}' の自動削除は現在無効です。")
            # try:
            #     logging.info(f"Gemini: アップロード済みファイル削除試行 - {audio_file_resource.name}")
            #     genai.delete_file(audio_file_resource.name) # 注意：同期/非同期を確認
            #     logging.info(f"Gemini: アップロード済みファイル削除完了 - {audio_file_resource.name}")
            # except Exception as delete_err:
            #     logging.error(f"Gemini: アップロード済みファイルの削除中にエラー - {audio_file_resource.name}: {delete_err}", exc_info=True)


# --- OpenAI ライブラリ設定 (DeepSeek API用) ---
try:
    from openai import OpenAI, APIError, RateLimitError, APITimeoutError, APIConnectionError, AuthenticationError, BadRequestError
except ImportError:
    logging.error("OpenAIライブラリが見つかりません。`pip install openai` を実行してください。")
    OpenAI = None
    APIError = RateLimitError = APITimeoutError = APIConnectionError = AuthenticationError = BadRequestError = Exception # type: ignore

# DeepSeek APIキーとベースURLを環境変数から取得
api_key_deepseek = os.getenv('DEEPSEEK') # 環境変数名を修正
base_url_deepseek = os.getenv('DEEPSEEK_BASE_URL', "https://api.deepseek.com/v1")

client_deepseek = None
deepseek_api_initialized = False

if not api_key_deepseek:
    logging.warning("環境変数 'DEEPSEEK_API_KEY' が設定されていません。DeepSeek APIは使用できません。")
elif OpenAI:
    try:
        client_deepseek = OpenAI(
            api_key=api_key_deepseek,
            base_url=base_url_deepseek,
            timeout=120.0,      # タイムアウトを延長 (120秒)
            max_retries=1,     # ライブラリによるリトライを1回だけ許可 (念のため)
        )
        logging.info(f"DeepSeek APIクライアント初期化完了 (URL: {base_url_deepseek})")
        deepseek_api_initialized = True
        # # 起動時の接続テストは必須ではないのでコメントアウト
        # try:
        #     models = client_deepseek.models.list()
        #     logging.debug(f"DeepSeek接続テスト成功。利用可能なモデル (一部): {[m.id for m in models.data[:5]]}")
        # except Exception as test_err:
        #      logging.error(f"DeepSeek APIへの接続テストに失敗しました: {test_err}")
        #      logging.error("APIキーまたはベースURLを確認してください。初期化は続行しますが、API呼び出しは失敗する可能性があります。")
    except Exception as e:
        logging.error(f"DeepSeek APIクライアントの初期化中にエラーが発生しました: {e}", exc_info=True)
else:
    pass # OpenAIライブラリがない場合


def call_deepseek_via_openai(prompt, model="deepseek-chat", max_tokens=3000, temperature=0.3, max_retries=2, initial_delay=3):
    """
    OpenAIライブラリ経由でDeepSeek APIを呼び出す関数。リトライ機能付き。
    成功時はLLMが生成したテキスト(JSON形式を期待)を、失敗時はNoneを返す。
    """
    if not deepseek_api_initialized or not client_deepseek:
        logging.error("DeepSeekクライアントが初期化されていないため、APIを呼び出せません。")
        return None
    if not OpenAI:
        logging.error("OpenAIライブラリがないため、DeepSeek APIを呼び出せません。")
        return None

    logging.info(f"DeepSeek: API呼び出し開始 (Model: {model}, Temp: {temperature}, MaxTokens: {max_tokens})")
    current_delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        logging.debug(f"DeepSeek: API呼び出し試行 {attempt + 1}/{max_retries + 1}")
        try:
            start_time = time.time()
            response = client_deepseek.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that strictly follows instructions and outputs responses in the specified format ONLY. Ensure the output is valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
                # response_format={"type": "json_object"}, # DeepSeekが対応していれば有効だが、未対応の場合エラーになるので注意
            )
            end_time = time.time()
            duration = end_time - start_time
            logging.debug(f"DeepSeek: API呼び出し成功 (所要時間: {duration:.2f}秒)")

            if not response.choices:
                logging.error("DeepSeek: API応答に choices が含まれていません。")
                last_exception = ValueError("API response missing 'choices'")
                # リトライしても無駄な可能性が高いので、待機時間を長くして最終試行に賭けるか、諦める
                wait_time = current_delay * 2
                if attempt < max_retries:
                     logging.info(f"DeepSeek: choicesがないためリトライします ({wait_time:.1f}秒後)...")
                     time.sleep(wait_time)
                     current_delay *= 1.5 # Backoff控えめ
                     continue # 次の試行へ
                else:
                     logging.error(f"DeepSeek: 最大リトライ回数 ({max_retries + 1}回) に達しました。choicesがありません。")
                     return None


            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            usage = response.usage

            logging.debug(f"DeepSeek: 応答取得完了 (Finish Reason: {finish_reason}, Tokens: {usage.total_tokens if usage else 'N/A'})")
            logging.debug(f"DeepSeek Generated Text (raw):\n---\n{content}\n---")

            if finish_reason == 'length':
                logging.warning(f"DeepSeek: max_tokens ({max_tokens}) に達したため、応答が途中で打ち切られている可能性があります。")

            # --- LLM応答からJSON部分を抽出 ---
            json_str = None
            # 優先度1: ```json ... ``` ブロック
            match_code_block = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', content, re.IGNORECASE | re.DOTALL)
            if match_code_block:
                json_str = match_code_block.group(1).strip()
                logging.info("DeepSeek: 応答から ```json ... ``` ブロックを抽出しました。")
            else:
                # 優先度2: 応答全体がJSON形式か (前後の空白は許容)
                json_match = re.search(r'^\s*([\[{].*[\]}])\s*$', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    logging.info("DeepSeek: 応答全体がJSON形式と判断しました。")

            if json_str:
                try:
                    # 有効なJSONかパースしてみる (パースするだけで、返すのは文字列)
                    json.loads(json_str)
                    logging.info("DeepSeek: 抽出/判断されたJSON文字列は有効です。")
                    # デバッグ用にファイル保存
                    output_filename = f"deepseek_output_{'summary' if 'summary' in prompt else 'quiz'}.json"
                    try:
                        with open(output_filename, "w", encoding="utf-8") as f:
                             f.write(json_str) # パースしたものではなく、抽出した文字列を保存
                        logging.debug(f"DeepSeek 応答 (JSON) を {output_filename} に保存しました。")
                    except IOError as e:
                        logging.error(f"DeepSeek 応答のファイル保存に失敗: {e}")
                    return json_str # 有効なJSON文字列を返す
                except json.JSONDecodeError as e:
                    logging.warning(f"DeepSeek: 抽出/判断されたJSON文字列のパースに失敗: {e}")
                    last_exception = e # エラー情報を保持
                    # パース失敗した場合、リトライする価値はあるかもしれない
            else:
                # JSONが見つからなかった場合
                logging.error("DeepSeek: 期待したJSON形式の応答（コードブロックまたは全体）が見つかりませんでした。")
                logging.error(f"DeepSeek Raw Response: {content.strip()}")
                last_exception = ValueError("No JSON found in response")
                # JSONが得られなかった場合もリトライする価値はあるかもしれない

            # リトライ処理 (JSONパース失敗 or JSONが見つからなかった場合)
            if attempt < max_retries:
                 wait_time = current_delay * (random.uniform(0.8, 1.2))
                 logging.info(f"DeepSeek: JSON取得/パース失敗のためリトライします ({wait_time:.1f}秒後)...")
                 time.sleep(wait_time)
                 current_delay *= 2 # Exponential Backoff
                 continue # 次の試行へ
            else:
                 # リトライ上限に達した場合
                 logging.error(f"DeepSeek: 最大リトライ回数 ({max_retries + 1}回) に達しました。有効なJSON応答を得られませんでした。")
                 return None # 失敗としてNoneを返す


        # --- エラーハンドリングとリトライ ---
        except AuthenticationError as e:
            logging.error(f"DeepSeek: 認証エラー (試行 {attempt + 1}): {e}. APIキーを確認してください。")
            return None # 認証エラーはリトライしない
        except BadRequestError as e:
             logging.error(f"DeepSeek: 不正なリクエストエラー (試行 {attempt + 1}): {e}. プロンプトやパラメータを確認してください。")
             # プロンプトが長すぎる場合などもここに来る可能性
             return None # リクエスト内容が悪い場合はリトライしない
        except RateLimitError as e:
            last_exception = e
            logging.warning(f"DeepSeek: APIレート制限エラーが発生しました (試行 {attempt + 1}): {e}")
            wait_time = current_delay * (random.uniform(1.0, 1.5)) # レート制限は少し長めに待つ
            logging.info(f"DeepSeek: レート制限のためリトライします ({wait_time:.1f}秒後)...")
        except (APITimeoutError, APIConnectionError) as e:
             last_exception = e
             logging.warning(f"DeepSeek: APIタイムアウト/接続エラーが発生しました (試行 {attempt + 1}): {e}")
             wait_time = current_delay * (random.uniform(0.8, 1.2))
             logging.info(f"DeepSeek: タイムアウト/接続エラーのためリトライします ({wait_time:.1f}秒後)...")
        except APIError as e: # その他のAPIエラー (例: 5xxサーバーエラー)
            last_exception = e
            logging.warning(f"DeepSeek: APIエラーが発生しました (試行 {attempt + 1}): HTTP Status={getattr(e, 'status_code', 'N/A')}, Type={getattr(e, 'type', 'N/A')}, Message={getattr(e, 'message', str(e))}")
            status_code = getattr(e, 'status_code', None)
            if status_code and 500 <= status_code < 600:
                 wait_time = current_delay * (random.uniform(0.8, 1.2))
                 logging.info(f"DeepSeek: サーバーエラー({status_code})のためリトライします ({wait_time:.1f}秒後)...")
            else:
                logging.error(f"DeepSeek: リトライ不可能なAPIエラー({status_code})です。")
                return None
        except Exception as e:
            last_exception = e
            logging.error(f"DeepSeek: API呼び出し中に予期せぬPythonエラーが発生しました (試行 {attempt + 1}): {type(e).__name__}: {e}", exc_info=True)
            wait_time = current_delay * (random.uniform(0.8, 1.2))
            logging.info(f"DeepSeek: 予期せぬエラーのためリトライします ({wait_time:.1f}秒後)...")

        # リトライ待機 (最終試行でなければ)
        if attempt < max_retries:
            time.sleep(wait_time)
            current_delay *= 2 # 次の遅延時間を増やす (Exponential Backoff)
        else:
            logging.error(f"DeepSeek: 最大リトライ回数 ({max_retries + 1}回) に達しました。API呼び出しを諦めます。")
            if last_exception:
                logging.error(f"DeepSeek: 最後に発生したエラー: {last_exception}")
            return None

    return None # この行には到達しないはず


def validate_summary_item(item, index):
    """要約リストの単一要素を検証するヘルパー関数"""
    if not isinstance(item, dict):
        raise ValueError(f"要約要素 {index + 1} が辞書形式ではありません。")
    required_keys = ["id", "type", "text"]
    missing_keys = [k for k in required_keys if k not in item]
    if missing_keys:
        raise ValueError(f"要約要素 {index + 1} に必須キー ({', '.join(missing_keys)}) が不足しています。")
    if not isinstance(item.get("id"), str) or not item.get("id"):
        raise ValueError(f"要約要素 {index + 1} の 'id' が空でない文字列ではありません。")
    if item.get("type") != "summary":
        raise ValueError(f"要約要素 {index + 1} の 'type' が 'summary' ではありません。 Actual: '{item.get('type')}'")
    if not isinstance(item.get("text"), str): # textは空文字列を許容
        raise ValueError(f"要約要素 {index + 1} の 'text' が文字列ではありません。")
    # 追加: textが過度に短い、または長すぎる場合のチェックなど？ (任意)
    return item

def generate_summary(transcript_or_json_str):
    """
    入力テキストまたはJSON文字列から、要約スライドのリストを生成する。
    Geminiが直接有効なJSONを返した場合はそれを使い、そうでなければDeepSeekに依頼する。
    成功時は要約リスト(Pythonオブジェクト)を、失敗時はNoneを返す。
    """
    logging.info("バックエンド: 要約生成処理 開始")
    validated_list = None
    transcript_text = transcript_or_json_str # DeepSeek用入力のデフォルト

    # 1. 入力がGeminiからの有効なJSONリストか試す
    if isinstance(transcript_or_json_str, str) and transcript_or_json_str.strip().startswith('['):
        try:
            parsed_data = json.loads(transcript_or_json_str)
            if isinstance(parsed_data, list):
                logging.debug("バックエンド: 入力はリスト形式のJSONです。Geminiからの応答として検証します。")
                current_validated_list = []
                if not parsed_data:
                     # 空リストは許容しないことにする
                     logging.warning("Gemini応答: JSONリストが空です。")
                     # raise ValueError("Gemini応答: JSONリストが空です。") # エラーにするか、DeepSeekに回すか
                     # DeepSeekに回すことにする
                else:
                     for i, item in enumerate(parsed_data):
                          current_validated_list.append(validate_summary_item(item, i)) # ヘルパー関数で検証
                     logging.info("バックエンド: Geminiからの直接生成された要約JSONを検証し、使用します。")
                     validated_list = current_validated_list # 検証成功
            else:
                logging.warning("バックエンド: Gemini応答はJSONでしたがリスト形式ではありません。DeepSeekに要約を依頼します。")
                # この場合、transcript_text は元の文字列のまま
        except (json.JSONDecodeError, TypeError) as e:
            # JSON文字列に見えたがパース失敗
            logging.info(f"バックエンド: 入力は有効な要約JSONリストではありません ({type(e).__name__}: {e})。DeepSeekに要約を依頼します。")
            # transcript_text は元の文字列のまま
        except ValueError as ve:
            # 形式はリストだが、中身の検証でエラー (validate_summary_item)
             logging.warning(f"バックエンド: Gemini応答JSONリストの検証に失敗: {ve}。DeepSeekに要約を依頼します。")
             # transcript_text は元の文字列のまま
    else:
        # 最初からJSON文字列ではなかった場合
        logging.info("バックエンド: 入力がJSONリスト形式ではないため、DeepSeekに要約を依頼します。")
        # transcript_text は元の文字列のまま

    # 2. Geminiの結果が使えなかった場合、DeepSeekに要約生成を依頼する
    if validated_list is None: # Geminiの結果が使えなかった場合のみ実行
        if not deepseek_api_initialized:
             logging.error("バックエンド: 要約生成失敗 (DeepSeekクライアント未初期化)")
             return None
        if not transcript_text: # DeepSeekへの入力が空でないか確認
             logging.error("バックエンド: 要約生成失敗 (DeepSeekへの入力テキストが空です)")
             return None


        logging.info("バックエンド: DeepSeek APIによる要約生成 開始")
        prompt = f"""
以下のテキストを分析し、内容の理解を助けるために、キーポイントを複数のスライド形式で要約してください。テキストが非常に長い場合は、主要な部分を網羅するようにしてください。

**厳格な出力形式の指示:**
結果は、**必ずJSONリスト `[]` のみ**としてください。JSONリストの前後に、**一切のテキスト（導入文、説明、補足、マークダウンの```json ... ```など）を含めないでください**。出力はJSONリストそのものでなければなりません。
リストの各要素は、**必ず**以下のキーを持つJSONオブジェクト `{{}}` でなければなりません：
- `"id"`: スライド番号を表す文字列。例のように `"s1"`, `"s2"`, `"s3"` と連番にしてください。
- `"type"`: 文字列であり、**必ず** `"summary"` という値にしてください。
- `"text"`: そのスライドの要約内容を含む文字列。簡潔かつ分かりやすく記述してください。テキスト内で改行する場合は `\\n` を使用してください。JSONとして有効なように、テキスト内の特殊文字（引用符など）は適切にエスケープしてください。

**必須のJSON出力形式の例（この例自体を出力に含めないでください）：**
[
  {{"id": "s1", "type": "summary", "text": "First summary point for slide 1."}},
  {{"id": "s2", "type": "summary", "text": "Second summary point.\\nThis one has a newline."}}
]

**入力テキスト:**
---
{transcript_text}
---

上記の指示に厳密に従い、要約スライドの**JSONリストのみ**を出力してください。出力は有効なJSONでなければなりません。他のテキストは一切含めないでください。
"""
        # DeepSeekへのリクエスト、長文に対応できるようmax_tokensを調整
        response_str = call_deepseek_via_openai(prompt, model="deepseek-chat", temperature=0.5, max_tokens=3000)

        if response_str:
            try:
                summary_list_deepseek = json.loads(response_str)
                if not isinstance(summary_list_deepseek, list):
                    raise ValueError("DeepSeek応答がリスト形式ではありません。")
                if not summary_list_deepseek:
                    raise ValueError("DeepSeek応答リストが空です。")

                validated_list_deepseek = []
                for i, item in enumerate(summary_list_deepseek):
                    validated_list_deepseek.append(validate_summary_item(item, i)) # ヘルパー関数で検証

                logging.info("バックエンド: DeepSeekによる要約生成完了 (JSONパース・検証成功)")
                return validated_list_deepseek # 検証済みのPythonリストを返す
            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"バックエンド: DeepSeek要約生成失敗 (JSONパースまたは検証エラー: {e})")
                logging.error(f"DeepSeek応答 (生文字列):\n---\n{response_str}\n---")
                return None
        else:
            logging.error("バックエンド: DeepSeek要約生成失敗 (API呼び出し失敗または有効なJSON応答なし)")
            return None
    else:
        # Geminiの結果が使えた場合
        return validated_list


def validate_quiz_item(item, index):
    """クイズリストの単一要素を検証するヘルパー関数"""
    if not isinstance(item, dict):
        raise ValueError(f"クイズ要素 {index + 1} が辞書形式ではありません。")
    required_keys = ["id", "type", "text", "options", "answer"]
    missing_keys = [k for k in required_keys if k not in item]
    if missing_keys:
        raise ValueError(f"クイズ要素 {index + 1} に必須キー ({', '.join(missing_keys)}) が不足しています。")
    if not isinstance(item.get("id"), str) or not item.get("id"):
        raise ValueError(f"クイズ要素 {index + 1} の 'id' が空でない文字列ではありません。")
    if item.get("type") != "question":
        raise ValueError(f"クイズ要素 {index + 1} の 'type' が 'question' ではありません。 Actual: '{item.get('type')}'")
    if not isinstance(item.get("text"), str) or not item.get("text"):
        raise ValueError(f"クイズ要素 {index + 1} の 'text' (質問文) が空でない文字列ではありません。")
    options = item.get("options")
    # オプションの数をチェック (例: 3個または4個を期待する場合)
    expected_options_count = 4 # 例として4択を期待
    if not isinstance(options, list) or len(options) != expected_options_count:
        raise ValueError(f"クイズ要素 {index + 1} の 'options' が正確に{expected_options_count}個の要素を持つリストではありません (現在: {len(options) if isinstance(options, list) else '非リスト'})。")
    if not all(isinstance(opt, str) and opt for opt in options):
        raise ValueError(f"クイズ要素 {index + 1} の 'options' の要素がすべて空でない文字列ではありません。")
    answer = item.get("answer")
    if not isinstance(answer, str) or not answer:
        raise ValueError(f"クイズ要素 {index + 1} の 'answer' が空でない文字列ではありません。")
    if answer not in options:
        # 答えが選択肢内にないのは致命的
        raise ValueError(f"クイズ要素 {index + 1} の 'answer' ('{answer}') が 'options' {options} 内に見つかりません。")
    return item


def generate_quiz(transcript_or_json_str):
    """
    入力テキストまたはJSON文字列から、クイズのリストを生成する (DeepSeek APIを使用)。
    成功時はクイズリスト(Pythonオブジェクト)を、失敗時はNoneを返す。
    """
    logging.info("バックエンド: クイズ生成処理 開始 (DeepSeek API)")

    transcript_text = transcript_or_json_str
    # 入力がJSON文字列かどうかをチェック（ログ出力用）
    is_json_input = False
    if isinstance(transcript_text, str):
        try:
            json.loads(transcript_text)
            if transcript_text.strip().startswith(('[', '{')):
                is_json_input = True
        except (json.JSONDecodeError, TypeError):
            pass
    if is_json_input:
        logging.warning("バックエンド: クイズ生成への入力がJSON形式でした。そのままテキストとして扱います。")

    if not deepseek_api_initialized:
         logging.error("バックエンド: クイズ生成失敗 (DeepSeekクライアント未初期化)")
         return None
    if not transcript_text:
        logging.error("バックエンド: クイズ生成失敗 (入力テキストが空です)")
        return None

    # --- クイズ設定 ---
    num_questions = 5  # 生成する問題数
    num_options = 4    # 各問題の選択肢の数

    logging.info(f"バックエンド: DeepSeek APIによるクイズ生成 開始 ({num_questions}問, {num_options}択)")
    prompt = f"""
以下のテキストを分析し、内容の理解度をテストするために、**正確に{num_questions}個**の多肢選択式クイズ問題を生成してください。各問題には、それぞれ**正確に{num_options}個**の異なる選択肢が必要です。

**厳格な出力形式の指示:**
結果は、**必ずJSONリスト `[]` のみ**としてください。JSONリストの前後に、**一切のテキスト（導入文、説明、補足、マークダウンの```json ... ```など）を含めないでください**。出力はJSONリストそのものでなければなりません。
リストの各要素は、**必ず**以下のキーを持つJSONオブジェクト `{{}}` でなければなりません：
- `"id"`: 質問番号を表す文字列。 `"q1"`, `"q2"`, ..., `"q{num_questions}"` と連番にしてください。
- `"type"`: 文字列であり、**必ず** `"question"` という値にしてください。
- `"text"`: 質問文そのものを含む文字列。具体的で明確な質問にしてください。
- `"options"`: 文字列のリスト `[]` であり、**正確に{num_options}個**の解答選択肢を含めてください。選択肢は互いに区別可能で、正解以外の選択肢（不正解の選択肢）ももっともらしいものにしてください。
- `"answer"`: 正しい答えを指定する文字列。この文字列は、**必ず**その質問の `"options"` リストに含まれる文字列のいずれかでなければなりません。

**必須のJSON出力形式の例（{num_questions}=3, {num_options}=4の場合 - この例自体を出力に含めないでください）：**
[
  {{"id": "q1", "type": "question", "text": "What was the primary focus of the discussion?", "options": ["Topic A", "Topic B", "Topic C", "Topic D"], "answer": "Topic B"}},
  {{"id": "q2", "type": "question", "text": "Which specific example was mentioned?", "options": ["Example X", "Example Y", "Example Z", "Example W"], "answer": "Example Y"}},
  {{"id": "q3", "type": "question", "text": "What is the recommended next action?", "options": ["Action 1", "Action 2", "Action 3", "Action 4"], "answer": "Action 1"}}
]

**入力テキスト:**
---
{transcript_text}
---

上記の指示に厳密に従ってください。**正確に{num_questions}個**のクイズ問題を生成し、**JSONリストのみ**を出力してください。他のテキストは一切含めないでください。出力は有効なJSONでなければなりません。
"""
    # クイズ生成は比較的短い応答で済むことが多いが、入力テキストによっては長くかかる可能性
    # max_tokens は num_questions や num_options に応じて調整
    max_tokens_quiz = num_questions * (150 + num_options * 50) # 大まかな目安 (質問文+選択肢)
    response_str = call_deepseek_via_openai(prompt, model="deepseek-chat", temperature=0.4, max_tokens=max_tokens_quiz)

    if response_str:
        try:
            quiz_list = json.loads(response_str)
            if not isinstance(quiz_list, list):
                raise ValueError("DeepSeek応答がリスト形式ではありません。")
            # 生成された問題数をチェック
            if len(quiz_list) != num_questions:
                logging.warning(f"DeepSeekが生成したクイズ数が指定と異なります (期待: {num_questions}, 実際: {len(quiz_list)})")
                # ここでエラーにするか、そのまま使うかは要件次第
                # if len(quiz_list) == 0: raise ValueError("DeepSeek応答クイズリストが空です。") # 空の場合はエラー
            if not quiz_list:
                 raise ValueError("DeepSeek応答クイズリストが空です。")

            validated_list = []
            for i, item in enumerate(quiz_list):
                 # IDを q1, q2... に強制的に振り直す (LLMが従わない場合があるため)
                 item['id'] = f'q{i+1}'
                 validated_list.append(validate_quiz_item(item, i)) # ヘルパー関数で検証

            logging.info(f"バックエンド: DeepSeekによるクイズ生成完了 ({len(validated_list)}問 JSONパース・検証成功)")
            return validated_list
        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"バックエンド: DeepSeekクイズ生成失敗 (JSONパースまたは検証エラー: {e})")
            logging.error(f"DeepSeek応答 (生文字列):\n---\n{response_str}\n---")
            return None
    else:
        logging.error("バックエンド: DeepSeekクイズ生成失敗 (API呼び出し失敗または有効なJSON応答なし)")
        return None


# --- Flask ルーティング (HTMLページ表示) ---

@app.route('/')
@app.route('/input')
def input_page():
    """入力画面を表示"""
    logging.debug("Routing: /input ページ表示")
    return render_template('input.html')

@app.route('/history')
def history_page():
    """履歴画面を表示"""
    logging.debug("Routing: /history ページ表示")
    history_items = []
    error_message = None

    # ↓↓↓ チェックを修正: 未設定または空文字列の場合のみエラーとする ↓↓↓
    if not GAS_WEB_APP_URL:
        logging.error("/history: GAS_WEB_APP_URLが設定されていません。") # エラーメッセージも少し具体的に
        error_message = "データベース接続設定が不完全なため、履歴を取得できません。(URL未設定)"
    else:
        # GASへのリクエスト処理
        try:
            logging.debug(f"/history: GASへの履歴取得リクエスト送信 - URL: {GAS_WEB_APP_URL}")
            # GETリクエスト (idパラメータなし) を送る
            gas_response = requests.get(GAS_WEB_APP_URL, timeout=60)
            gas_response.raise_for_status() # HTTPエラーチェック

            gas_result = gas_response.json()
            logging.debug(f"/history: GASからの応答受信: {gas_result}")

            # GAS応答を検証 (変更なし)
            if gas_result.get("success") and isinstance(gas_result.get("data"), list):
                history_items = gas_result["data"]
                logging.info(f"/history: GASからの履歴取得 成功 ({len(history_items)}件)")
            elif not gas_result.get("success"):
                gas_error_msg = gas_result.get('message', 'GASからの履歴取得中に不明なエラーが発生しました。')
                logging.error(f"/history: GASからの履歴取得失敗 (GAS側エラー): {gas_error_msg}")
                error_message = f"データベースエラー: {gas_error_msg}"
            else:
                logging.error(f"/history: GASからの応答形式が予期しないものです (dataがリストでない等)。")
                error_message = "データベースからの応答形式が不正です。"

        except requests.exceptions.Timeout:
             logging.error("/history: GASへの接続がタイムアウトしました。")
             error_message = "データベースへの接続がタイムアウトしました。"
        except requests.exceptions.HTTPError as http_err:
             status_code = http_err.response.status_code if http_err.response else "N/A"
             logging.error(f"/history: GASへの接続でHTTPエラーが発生: Status={status_code}, Error={http_err}")
             error_message = f"データベース接続エラー (HTTP {status_code})。"
        except requests.exceptions.RequestException as req_err:
             logging.error(f"/history: GASへの接続中にネットワークエラー等が発生: {req_err}")
             error_message = f"データベース接続エラー: {req_err}"
        except json.JSONDecodeError as json_err:
             raw_gas_response = gas_response.text if 'gas_response' in locals() else "N/A"
             logging.error(f"/history: GASからの応答JSONのパースに失敗: {json_err}")
             logging.error(f"GAS Raw Response: {raw_gas_response[:500]}...")
             error_message = "データベースからの応答形式が不正です。"
        except Exception as e:
             logging.error(f"/history: 履歴取得中に予期せぬエラーが発生: {e}", exc_info=True)
             error_message = "サーバー内部エラーが発生しました。"

    # 取得したデータまたはエラーメッセージをテンプレートに渡す (変更なし)
    return render_template('history.html', history_items=history_items, error_message=error_message)
# 他のルート (@app.route('/') や @app.route('/learning') など) は変更なし
# APIエンドポイント (@app.route('/api/generate') など) も変更なし
@app.route('/learning')
def learning_page():
    """学習画面を表示"""
    content_id = request.args.get('id')
    logging.debug(f"Routing: /learning ページ表示リクエスト (Content ID: {content_id})")
    if not content_id:
         logging.warning("学習画面リクエストで content_id が指定されていません。")
         return render_template('learning.html', error_message="表示するコンテンツIDが指定されていません。", content_id=None, title="エラー")
    # タイトルはJSがAPIから取得して設定する想定
    return render_template('learning.html', content_id=content_id, title="学習コンテンツ読み込み中...")

@app.route('/settings')
def settings_page():
    """設定画面を表示"""
    logging.debug("Routing: /settings ページ表示")
    return render_template('settings.html')

# --- Flask APIエンドポイント ---

@app.route('/api/generate', methods=['POST'])
def generate_content():
    """
    YouTube URLを受け取り、音声抽出、文字起こし、要約、クイズ生成を行い、
    結果をGASに保存し、クライアントにも返すAPI。
    """
    start_time_generate = time.time()
    logging.info("API /api/generate: リクエスト受信")

    if not request.is_json:
        logging.warning("API /api/generate: リクエスト形式が不正 (非JSON)")
        return jsonify({"success": False, "message": "リクエストはJSON形式である必要があります。"}), 400

    data = request.get_json()
    youtube_url = data.get('url')

    if not youtube_url:
        logging.warning("API /api/generate: URLが指定されていません")
        return jsonify({"success": False, "message": "YouTubeのURLが指定されていません。"}), 400

    # URL形式チェック (yt-dlpに任せるので緩め)
    if not isinstance(youtube_url, str) or 'youtube.com' not in youtube_url and 'youtu.be' not in youtube_url:
         logging.warning(f"API /api/generate: YouTube URLとして疑わしい形式です: {youtube_url}")
         # ここでエラーにするか、yt-dlpのエラーに任せるか選択
         # return jsonify({"success": False, "message": "有効なYouTubeのURLを指定してください。"}), 400

    logging.info(f"API /api/generate: URL='{youtube_url}' で処理開始")

    audio_path = None
    generated_data = None
    content_id = None
    video_info = None # 動画情報を格納

    try:
        # --- 1. 音声抽出 & 動画情報取得 ---
        step_start_time = time.time()
        logging.info("API /api/generate: (1/5) 音声抽出 & 動画情報取得 開始")
        # download_and_extract_audio は (audio_path, video_info) を返すように修正
        audio_path, video_info = download_and_extract_audio(youtube_url)
        if not audio_path:
            # video_info にエラーメッセージなどが入っている可能性もあるが、audio_pathがなければ失敗
            raise ValueError("音声ファイルの抽出に失敗しました。URLが正しいか、動画が利用可能か確認してください。")
        logging.info(f"API /api/generate: (1/5) 音声抽出完了 - Path: {audio_path} (所要時間: {time.time() - step_start_time:.2f}秒)")
        if not video_info: # audio_pathがあってもvideo_infoがない場合 (通常はありえないはず)
             video_info = {'title': '不明な動画', 'thumbnail': None}
             logging.warning("API /api/generate: 動画情報の取得に失敗しましたが、音声抽出は成功しました。")


        # --- 2. 文字起こし・初期要約 (Gemini) ---
        step_start_time = time.time()
        logging.info("API /api/generate: (2/5) 文字起こし・初期要約 (Gemini) 開始")
        transcript_or_summary_json = transcribe_audio(audio_path)
        if transcript_or_summary_json is None:
             raise ValueError("Geminiによる文字起こし・初期要約処理に失敗しました。APIキーやクォータを確認してください。")
        if not transcript_or_summary_json:
             logging.warning("API /api/generate: Geminiからの応答が空でした。")
             raise ValueError("Geminiによる文字起こし・初期要約結果が空です。音声が無音でないか確認してください。")
        logging.info(f"API /api/generate: (2/5) 文字起こし・初期要約 (Gemini) 完了 (所要時間: {time.time() - step_start_time:.2f}秒)")

        # --- 3. 最終的な要約リスト生成 (Gemini結果 or DeepSeek) ---
        step_start_time = time.time()
        logging.info("API /api/generate: (3/5) 最終要約リスト生成 開始")
        summary_items = generate_summary(transcript_or_summary_json)
        if not summary_items:
            # generate_summary内でエラーログが出力されているはず
            raise ValueError("要約リストの生成に失敗しました。モデルの応答形式を確認してください。")
        logging.info(f"API /api/generate: (3/5) 最終要約リスト生成 完了 ({len(summary_items)}項目) (所要時間: {time.time() - step_start_time:.2f}秒)")

        # --- 4. クイズ生成 (DeepSeek) ---
        step_start_time = time.time()
        logging.info("API /api/generate: (4/5) クイズ生成 開始")
        # クイズ生成にはGeminiの応答（JSON文字列またはテキスト）を使う
        question_items = generate_quiz(transcript_or_summary_json)
        if not question_items:
             raise ValueError("クイズの生成に失敗しました。モデルの応答形式を確認してください。")
        logging.info(f"API /api/generate: (4/5) クイズ生成 完了 ({len(question_items)}項目) (所要時間: {time.time() - step_start_time:.2f}秒)")

        # --- 成功データの準備 ---
        content_id = f"cont_{int(time.time())}_{random.randint(1000, 9999)}"
        # yt-dlpから取得した情報を使用
        video_title = video_info.get('title', f"生成コンテンツ {content_id[-4:]}")
        # サムネイルURLもyt-dlpから取得、なければデフォルト
        thumbnail_url = video_info.get('thumbnail')
        if not thumbnail_url and video_info.get('id'):
             # yt-dlpで取得できなかった場合、標準的なURLを試す
             thumbnail_url = f"https://i.ytimg.com/vi/{video_info['id']}/mqdefault.jpg"

        generated_data = {
            "id": content_id,
            "title": video_title,
            "thumbnail": thumbnail_url or '', # Noneではなく空文字を渡す
            "summary": summary_items,   # Pythonリスト
            "questions": question_items # Pythonリスト
        }
        logging.debug(f"API /api/generate: 生成データ準備完了 (ID: {content_id})")

        # --- 5. GASにデータを保存 ---
        step_start_time = time.time()
        logging.info("API /api/generate: (5/5) GASへのデータ保存 開始")
        # GAS URLのチェックを強化
        if not GAS_WEB_APP_URL or 'YOUR_PLACEHOLDER_GAS_URL' in GAS_WEB_APP_URL or not GAS_WEB_APP_URL.startswith('https://script.google.com/macros/s/'):
            logging.warning("API /api/generate: GAS_WEB_APP_URLが無効または設定されていません。データは保存されません。")
            # 保存失敗でも処理は続行し、生成データを返す
        else:
            try:
                headers = {'Content-Type': 'application/json'}
                # GASのdoPostに送信するデータ (Python dict)
                # GAS側で summary と questions を stringify するので、ここではリストのまま送る
                payload_to_gas = generated_data.copy() # 元のデータを変更しないようにコピー

                gas_response = requests.post(
                    GAS_WEB_APP_URL,
                    headers=headers,
                    data=json.dumps(payload_to_gas), # Python dictをJSON文字列に変換
                    timeout=60 # GASのタイムアウトを少し長めに設定 (60秒)
                )
                gas_response.raise_for_status()

                gas_result = gas_response.json()
                if gas_result.get("success"):
                    returned_content_id = gas_result.get("content_id")
                    logging.info(f"API /api/generate: (5/5) GASへのデータ保存 成功 (GASが返したID: {returned_content_id}) (所要時間: {time.time() - step_start_time:.2f}秒)")
                    # Flask側で生成したIDとGASが返したIDが一致するか確認 (任意)
                    if returned_content_id != content_id:
                         logging.warning(f"GAS保存後のContent ID不一致: Flask側={content_id}, GAS側={returned_content_id}")
                else:
                    gas_error_msg = gas_result.get('message', 'GAS側でエラーが発生しました。')
                    logging.error(f"API /api/generate: GASへのデータ保存失敗 (GAS応答): {gas_error_msg}")
                    # 警告に留める

            except requests.exceptions.Timeout:
                 logging.error("API /api/generate: GASへの接続がタイムアウトしました。データは保存されませんでした。")
            except requests.exceptions.RequestException as req_err:
                # HTTPエラーの詳細（ステータスコード、応答内容）をログに出力
                status_code = req_err.response.status_code if req_err.response else "N/A"
                response_text = req_err.response.text if req_err.response else "N/A"
                logging.error(f"API /api/generate: GASへのデータ保存中にネットワーク/HTTPエラーが発生: Status={status_code}, Error={req_err}. Response: {response_text[:500]}...") # 応答が長い場合に切り詰める
            except json.JSONDecodeError as json_err:
                 logging.error(f"API /api/generate: GASからの応答JSONのパースに失敗: {json_err}")
                 # GASからの生応答を出力 (gas_response 変数が存在する場合)
                 raw_gas_response = "N/A"
                 if 'gas_response' in locals() and hasattr(gas_response, 'text'):
                     raw_gas_response = gas_response.text
                 logging.error(f"GAS Raw Response: {raw_gas_response[:500]}...")
            # GAS保存失敗は警告として処理を続行

        # --- 最終的な成功応答 ---
        total_duration = time.time() - start_time_generate
        logging.info(f"API /api/generate: 全処理成功 (Total Time: {total_duration:.2f}秒) - Content ID: {content_id}")
        # 生成したデータを返す (GAS保存の成否に関わらず)
        return jsonify({"success": True, "data": generated_data}), 200

    except ValueError as ve: # バックエンド処理中の予期されたエラー
        total_duration = time.time() - start_time_generate
        logging.error(f"API /api/generate: 処理中にエラーが発生しました (ValueError): {ve} (Total Time: {total_duration:.2f}秒)")
        # ユーザーフレンドリーなメッセージを返す
        return jsonify({"success": False, "message": f"コンテンツ生成エラー: {str(ve)}"}), 400 # Bad Request
    except Exception as e: # その他の予期せぬエラー
        total_duration = time.time() - start_time_generate
        logging.error(f"API /api/generate: 処理中に予期せぬエラーが発生しました: {type(e).__name__}: {e} (Total Time: {total_duration:.2f}秒)", exc_info=True)
        return jsonify({"success": False, "message": "サーバー内部で予期せぬエラーが発生しました。管理者にご連絡ください。"}), 500 # Internal Server Error

    finally:
        # --- 一時音声ファイルの削除 ---
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logging.info(f"一時音声ファイル {audio_path} を削除しました。")
            except OSError as rm_err:
                logging.error(f"一時音声ファイル {audio_path} の削除に失敗しました: {rm_err}")


@app.route('/api/learning/<content_id>', methods=['GET'])
def get_learning_content(content_id):
    """
    指定されたIDの学習コンテンツ（要約とクイズ）をGASから取得するAPI。
    GASのdoGetは、指定IDのデータを {success: true, data: {id:.., title:.., ..., items: [...], totalItems: ...}} の形で返す想定。
    """
    start_time_learning = time.time()
    logging.info(f"API /api/learning/{content_id}: リクエスト受信")

    if not content_id:
        logging.warning(f"API /api/learning: content_id が指定されていません。")
        return jsonify({"success": False, "message": "コンテンツIDが指定されていません。"}), 400

    # GAS URLのチェック
    if not GAS_WEB_APP_URL or 'YOUR_PLACEHOLDER_GAS_URL' in GAS_WEB_APP_URL or not GAS_WEB_APP_URL.startswith('https://script.google.com/macros/s/'):
        logging.error(f"API /api/learning/{content_id}: GAS_WEB_APP_URLが無効または設定されていません。")
        return jsonify({"success": False, "message": "データベース接続設定が不完全です。"}), 500

    try:
        params = {'id': content_id}
        logging.debug(f"API /api/learning/{content_id}: GASへのデータ取得リクエスト送信 - URL: {GAS_WEB_APP_URL} Params: {params}")

        gas_response = requests.get(GAS_WEB_APP_URL, params=params, timeout=60) # タイムアウト60秒
        gas_response.raise_for_status()

        gas_result = gas_response.json()
        logging.debug(f"API /api/learning/{content_id}: GASからの応答受信 (raw): {gas_result}")

        # GAS側の応答形式を検証 (success と data が存在するか)
        if "success" in gas_result and "data" in gas_result:
             if gas_result["success"] and gas_result["data"] is not None:
                 # GASから受け取った 'data' フィールドの中身をそのままクライアントに返す
                 response_data = gas_result["data"]
                 # 'items' が存在し、リストであることを念のため確認
                 if isinstance(response_data.get("items"), list):
                     duration = time.time() - start_time_learning
                     logging.info(f"API /api/learning/{content_id}: GASからのデータ取得 成功 ({response_data.get('totalItems', '?')}項目) (Total Time: {duration:.2f}秒)")
                     return jsonify({"success": True, "data": response_data}), 200
                 else:
                     logging.error(f"API /api/learning/{content_id}: GAS応答の 'data.items' がリスト形式ではありません。")
                     return jsonify({"success": False, "message": "データベースからの応答形式が不正です (items)。"}), 500
             elif not gas_result["success"]:
                 # GAS側で success: false が返ってきた場合
                 gas_error_msg = gas_result.get('message', 'GASからのデータ取得中に不明なエラーが発生しました。')
                 if "not found" in gas_error_msg.lower():
                     logging.warning(f"API /api/learning/{content_id}: コンテンツが見つかりませんでした (GAS応答)")
                     return jsonify({"success": False, "message": f"指定されたコンテンツID '{content_id}' が見つかりません。"}), 404 # Not Found
                 else:
                     logging.error(f"API /api/learning/{content_id}: GASからのデータ取得失敗 (GAS側エラー): {gas_error_msg}")
                     return jsonify({"success": False, "message": f"データベースエラー: {gas_error_msg}"}), 500 # Internal Server Error (or Bad Gateway 502)
             else: # success: true だけど data が null の場合 (GASがそのように返す場合)
                 logging.warning(f"API /api/learning/{content_id}: GASは成功と応答しましたが、データが見つかりませんでした (data is null)。")
                 return jsonify({"success": False, "message": f"指定されたコンテンツID '{content_id}' が見つかりません。"}), 404 # Not Found
        else:
            # success または data フィールド自体が欠落している場合
            logging.error(f"API /api/learning/{content_id}: GASからの応答形式が予期しないものです (success/data欠落)。 Response: {gas_result}")
            return jsonify({"success": False, "message": "データベースからの応答形式が不正です。"}), 500

    except requests.exceptions.Timeout:
         logging.error(f"API /api/learning/{content_id}: GASへの接続がタイムアウトしました。")
         return jsonify({"success": False, "message": "データベースへの接続がタイムアウトしました。"}), 504 # Gateway Timeout
    except requests.exceptions.HTTPError as http_err:
         status_code = http_err.response.status_code if http_err.response else "N/A"
         response_text = http_err.response.text[:500] if http_err.response else "N/A"
         logging.error(f"API /api/learning/{content_id}: GASへの接続でHTTPエラーが発生: Status={status_code}, Error={http_err}. Response: {response_text}...")
         if status_code == 404:
              return jsonify({"success": False, "message": "データベースのエンドポイントが見つかりません。"}), 404
         else:
              return jsonify({"success": False, "message": f"データベース接続エラー (HTTP {status_code})。"}), 502 # Bad Gateway が適切か
    except requests.exceptions.RequestException as req_err:
         logging.error(f"API /api/learning/{content_id}: GASへの接続中にネットワークエラー等が発生: {req_err}")
         return jsonify({"success": False, "message": f"データベース接続エラー: {req_err}"}), 500
    except json.JSONDecodeError as json_err:
         raw_gas_response = "N/A"
         if 'gas_response' in locals() and hasattr(gas_response, 'text'):
             raw_gas_response = gas_response.text
         logging.error(f"API /api/learning/{content_id}: GASからの応答JSONのパースに失敗: {json_err}")
         logging.error(f"GAS Raw Response: {raw_gas_response[:500]}...")
         return jsonify({"success": False, "message": "データベースからの応答形式が不正です。"}), 500
    except Exception as e:
         logging.error(f"API /api/learning/{content_id}: コンテンツ取得中に予期せぬエラーが発生: {e}", exc_info=True)
         return jsonify({"success": False, "message": f"サーバー内部エラーが発生しました。"}), 500


# --- アプリケーションの実行 ---
if __name__ == '__main__':
    print("*"*60)
    print("Flaskアプリケーション起動準備")
    print("*"*60)

    # --- 環境変数チェック ---
    print("環境変数チェック:")
    # 必須の環境変数リスト (変更なし)
    required_env_vars = ['GEMINI_API_KEY', 'DEEPSEEK_API_KEY', 'GAS_WEB_APP_URL']
    missing_vars = []
    env_vars_status = {}

    # GEMINI_API_KEY チェック (変更なし)
    gemini_key = os.getenv('GEMINI')
    if not gemini_key:
        missing_vars.append('GEMINI')
        env_vars_status['GEMINI_API_KEY'] = "未設定"
    else:
        env_vars_status['GEMINI_API_KEY'] = "設定済み"

    # DEEPSEEK_API_KEY チェック (変更なし)
    deepseek_key = os.getenv('DEEPSEEK')
    if not deepseek_key:
        missing_vars.append('DEEPSEEK_API_KEY')
        env_vars_status['DEEPSEEK_API_KEY'] = "未設定"
    else:
        env_vars_status['DEEPSEEK_API_KEY'] = "設定済み"

    # GAS_WEB_APP_URL チェック (文字列チェックを削除)
    gas_url = os.getenv('GAS_WEB_APP_URL')
    if not gas_url: # 未設定または空文字列の場合のみチェック
        missing_vars.append('GAS_WEB_APP_URL')
        env_vars_status['GAS_WEB_APP_URL'] = "未設定"
    else: # 何らかの値が設定されていればOKとする
        # 設定されている場合は、その値をそのまま表示
        env_vars_status['GAS_WEB_APP_URL'] = f"設定済み: {gas_url}"

    # 結果表示 (変更なし)
    print(f"  GEMINI_API_KEY: {env_vars_status['GEMINI_API_KEY']}")
    print(f"  DEEPSEEK_API_KEY: {env_vars_status['DEEPSEEK_API_KEY']}")
    print(f"  GAS_WEB_APP_URL: {env_vars_status['GAS_WEB_APP_URL']}") # 設定されていればURLが表示される

    # 未設定の場合の警告メッセージ (GAS_WEB_APP_URLの内容に関する警告は削除)
    if missing_vars:
        print("\n[警告] 以下の必須環境変数が設定されていません:")
        # missing_vars に GAS_WEB_APP_URL が含まれていれば表示される
        for var in missing_vars:
            print(f"  - {var}")
        print("関連する機能が動作しない可能性があります。")
    else:
         # すべて設定されていればメッセージを表示
         print("\n必要な環境変数は設定されているようです。")

    print("-"*60)

    # --- 起動 --- (以降変更なし)
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ['true', '1']
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 7860))

    print(f"Flaskサーバーを起動します...")
    print(f"  モード: {'デバッグ' if debug_mode else '本番'}")
    print(f"  ホスト: {host}")
    print(f"  ポート: {port}")
    try:
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"  アクセスURL (例): http://127.0.0.1:{port}/ または http://{local_ip}:{port}/")
    except:
        print(f"  アクセスURL: http://{host}:{port}/")
    print("*"*60)

    app.run(debug=debug_mode, host=host, port=port)