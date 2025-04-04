import os
import time
import random
from flask import Flask, render_template, request, jsonify
import yt_dlp 
import requests
import base64
from google import genai
import google.generativeai as genai
# --- アプリケーション設定 ---
app = Flask(__name__)
# セキュリティのため、実際の運用ではランダムなキーを設定してください
app.secret_key = os.urandom(24)

# --- バックエンド処理関数のプレースホルダー ---
# (これらの関数は将来的に別ファイルに切り出すのが良いでしょう)

import logging
import traceback

# ログ設定（DEBUGレベルで詳細ログを出力）
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def download_and_extract_audio(youtube_url):
    """
    yt-dlpを使って動画をダウンロードし、音声を抽出する。
    成功したら音声ファイルパスを、失敗したらNoneを返す。
    詳細なエラー情報はログに出力されます。
    """
    output_dir = 'downloads'
    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
        'verbose': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logging.debug(f"開始: {youtube_url} の音声抽出")
            info_dict = ydl.extract_info(youtube_url, download=True)
            audio_file = ydl.prepare_filename(info_dict)
            audio_file = os.path.splitext(audio_file)[0] + '.mp3'
            logging.info(f"音声抽出完了: {audio_file}")
            return audio_file
    except Exception as e:
        logging.error("音声抽出中にエラーが発生しました。")
        logging.error(traceback.format_exc())
        return None

def transcribe_audio(audio_path):
    """
    Gemini 2.5 Pro の文字起こしAPIを使用して、音声ファイルの文字起こしを実行します。
    この実装では google.genai ライブラリを利用してAPI呼び出しを行います。
    """
    # 実際のAPIキーに置き換えてください
    api_key = ""
    genai.configure(api_key=api_key)
    # ファイルのアップロード
    audio_file = genai.upload_file(path=audio_path)
    # モデルの準備
    model = genai.GenerativeModel("models/gemini-1.5-pro-latest")

    # プロンプトの準備
    response = model.generate_content(
        [
            "次の音声を文字起こししてください。",
            audio_file
        ]
    )
    print(response.text)
    return response.text
    # 文字起こし結果を取得    
import json
import time
import os
import re
import random


try:
    from openai import OpenAI, APIError, RateLimitError, APITimeoutError, APIConnectionError
except ImportError:
    print("エラー: 'openai' ライブラリが見つかりません。")
    print("pip install openai を実行してください。")
    # ライブラリがない場合は実行できないため、Noneを設定するなどして対応
    OpenAI = None
    APIError = None # type: ignore
    RateLimitError = None # type: ignore
    APITimeoutError = None # type: ignore
    APIConnectionError = None # type: ignore

# --- OpenAI クライアントの初期化 (DeepSeek API向け) ---
api_key = ''
# DeepSeek APIのエンドポイント (公式ドキュメント等で確認してください)
# v1を含める場合と含めない場合があるようです。どちらかで試してください。
base_url = "https://api.deepseek.com/v1"# または "https://api.deepseek.com"

client = None
api_initialized = False

if not api_key:
    print("警告: 環境変数 DEEPSEEK_API_KEY が設定されていません。")
elif OpenAI:
    try:
        # OpenAIクライアントをDeepSeek用に設定
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            # 必要に応じてタイムアウト設定 (例: 接続10秒, 読み取り60秒)
            timeout=60.0,
            max_retries=0 # リトライは自前で実装するため、ライブラリ側は0に
        )
        # 簡単な接続テスト（例: モデルリスト取得）
        # client.models.list() # これがエラーなく実行できれば初期化成功とみなす
        print(f"OpenAIクライアントをDeepSeek API ({base_url}) 用に初期化成功。")
        api_initialized = True
    except Exception as e:
        print(f"エラー: OpenAIクライアントの初期化に失敗しました: {e}")
        print("APIキーまたはAPIベースURLを確認してください。")
else:
    # openai ライブラリがインポートできなかった場合
    pass

def call_deepseek_via_openai(prompt, model="deepseek-chat", max_tokens=1500, temperature=0.3, max_retries=2, initial_delay=2):
    """
    OpenAIライブラリ経由でDeepSeek APIを呼び出す関数。
    成功時はLLMが生成したテキスト(JSON形式を期待)を、失敗時はNoneを返す。
    リトライ機能を含む。
    """
    if not api_initialized or not client:
        print("エラー: OpenAIクライアントが初期化されていません。APIキーの設定やライブラリのインストールを確認してください。")
        return None

    print(f"バックエンド: DeepSeek API 呼び出し開始 (via OpenAI Lib, model={model}, temp={temperature}, max_tokens={max_tokens})")
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            print(f"バックエンド: (試行 {attempt + 1}/{max_retries + 1}) API呼び出し中...")
            start_time = time.time()

            # OpenAIライブラリのメソッドで呼び出し
            response = client.chat.completions.create(
                model=model, # DeepSeekのモデル名を指定
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
                # response_format={"type": "json_object"} # OpenAI 1.x 形式でJSONモード指定 (DeepSeek APIが対応していれば)
            )
            end_time = time.time()
            duration = end_time - start_time
            print(f"バックエンド: API呼び出し成功 (所要時間: {duration:.2f}秒)")

            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            total_tokens = response.usage.total_tokens if response.usage else 'N/A'
            print(f"バックエンド: 応答取得完了 (finish_reason: {finish_reason}, total_tokens: {total_tokens})")

            if finish_reason == 'length':
                print("警告: max_tokensに達したため、応答が途中で打ち切られている可能性があります。")

            # --- LLM応答からJSON部分を抽出 ---
            # (抽出ロジックは前回と同様)
            match_code_block = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', content, re.IGNORECASE | re.DOTALL)
            if match_code_block:
                json_str = match_code_block.group(1).strip()
                print("バックエンド: 応答から ```json ... ``` ブロックを抽出しました。")
                try:
                    json.loads(json_str)
                    return json_str
                except json.JSONDecodeError:
                    print("バックエンド: コードブロック内を抽出しましたが、有効なJSONではありませんでした。応答全体を試します。")

            json_match = re.search(r'^\s*([\[{].*[\]}])\s*$', content, re.DOTALL)
            if json_match:
                potential_json = json_match.group(1)
                try:
                    json.loads(potential_json)
                    print("バックエンド: 応答全体がJSON形式（または前後に空白のみ）と判断しました。")
                    return potential_json
                except json.JSONDecodeError:
                     print("バックエンド: 応答全体がJSON形式に見えましたが、パースに失敗しました。")

            print("バックエンド: 特定のJSONブロックを見つけられませんでした。整形されていない可能性がある応答全体を返します。")
            return content.strip()

        except RateLimitError as e:
            last_exception = e
            print(f"バックエンド: DeepSeek API レート制限エラーが発生しました (試行 {attempt + 1}): {e}")
            if attempt < max_retries:
                # RateLimitErrorの場合、ヘッダーにリトライまでの推奨待機時間が含まれる場合がある (が、ここでは固定+Exponential Backoff)
                wait_time = delay * (random.uniform(0.8, 1.2)) # Jitter
                print(f"バックエンド: リトライします ({wait_time:.1f}秒後)...")
                time.sleep(wait_time)
                delay *= 2
            else:
                print("バックエンド: 最大リトライ回数に達しました。")
                return None
        except (APITimeoutError, APIConnectionError) as e:
             last_exception = e
             print(f"バックエンド: DeepSeek API タイムアウト/接続エラーが発生しました (試行 {attempt + 1}): {e}")
             if attempt < max_retries:
                 wait_time = delay * (random.uniform(0.8, 1.2)) # Jitter
                 print(f"バックエンド: リトライします ({wait_time:.1f}秒後)...")
                 time.sleep(wait_time)
                 delay *= 2
             else:
                 print("バックエンド: 最大リトライ回数に達しました。")
                 return None
        except APIError as e: # その他のAPIエラー (認証エラー、サーバーエラーなど)
            last_exception = e
            print(f"バックエンド: DeepSeek API エラーが発生しました (試行 {attempt + 1}): HTTP Status={e.status_code}, Type={e.type}, Message={e.message}")
            # 5xx系のサーバーエラーはリトライする価値があるかもしれない
            if e.status_code and 500 <= e.status_code < 600:
                 if attempt < max_retries:
                     wait_time = delay * (random.uniform(0.8, 1.2)) # Jitter
                     print(f"バックエンド: サーバーエラーのためリトライします ({wait_time:.1f}秒後)...")
                     time.sleep(wait_time)
                     delay *= 2
                 else:
                     print("バックエンド: 最大リトライ回数に達しました。")
                     return None
            else: # 認証エラー(401)やリクエスト不正(400)などはリトライしない
                print("バックエンド: リトライ不可能なAPIエラーです。")
                return None
        except Exception as e:
            # その他の予期せぬエラー
            last_exception = e
            print(f"バックエンド: API呼び出し中に予期せぬエラーが発生しました (試行 {attempt + 1}): {type(e).__name__}: {e}")
            if attempt < max_retries:
                 wait_time = delay * (random.uniform(0.8, 1.2)) # Jitter
                 print(f"バックエンド: リトライします ({wait_time:.1f}秒後)...")
                 time.sleep(wait_time)
                 delay *= 2
            else:
                print("バックエンド: 最大リトライ回数に達しました。")
                return None

    # すべてのリトライが失敗した場合
    print(f"バックエンド: API呼び出し失敗 ({max_retries + 1}回の試行後)")
    if last_exception:
        print(f"最後に発生したエラー: {last_exception}")
    return None


# --- generate_summary と generate_quiz 関数 ---
# これらの関数は内部で call_deepseek_real の代わりに call_deepseek_via_openai を呼び出すように変更します。
# プロンプトやJSONの検証ロジックは同じです。

def generate_summary(transcript):
    """
    文字起こしテキストを要約LLM (DeepSeek API via OpenAI Lib) に送信する。
    成功したら要約スライドのリスト (Pythonオブジェクト) を、失敗したらNoneを返す。
    """
    print("バックエンド: 要約生成開始 (DeepSeek API via OpenAI Lib)")
    # プロンプトは前回と同じ
    prompt = f"""
以下の会議の文字起こしテキストを分析し、内容を理解するための重要なポイントをまとめた要約スライドを3つ生成してください。

**出力形式の厳格な指示:**
結果は必ずJSON形式のリストとして出力してください。他のテキスト（例: 説明文、前置きなど）は一切含めないでください。
リストの各要素はJSONオブジェクト（辞書）で、以下のキーを含みます:
- "id": 文字列。 "s1", "s2", "s3" のように連番を振ってください。
- "type": 文字列。 必ず "summary" としてください。
- "text": 文字列。 スライドの本文（要約内容）を入れてください。改行は \\n を使用してください。

**出力形式の例 (この例自身は出力に含めないでください):**
[
  {{"id": "s1", "type": "summary", "text": "スライド1の要約テキスト..."}},
  {{"id": "s2", "type": "summary", "text": "スライド2の要約テキスト..."}},
  {{"id": "s3", "type": "summary", "text": "スライド3の要約テキスト..."}}
]

**文字起こしテキスト:**
---
{transcript}
---

上記の指示に従い、JSON形式の要約スライドリストのみを出力してください。説明や前置きは不要です。
"""
    # 呼び出す関数を変更
    response_str = call_deepseek_via_openai(prompt, temperature=0.5, max_tokens=1000)

    # 以降のJSONパースと検証ロジックは前回と同じ
    if response_str:
        try:
            summary_list = json.loads(response_str)
            if not isinstance(summary_list, list): raise ValueError("応答がリスト形式ではありません。")
            if not summary_list: raise ValueError("応答リストが空です。")
            validated_list = []
            for i, item in enumerate(summary_list):
                if not isinstance(item, dict): raise ValueError(f"要素 {i} が辞書形式ではありません。")
                if not all(k in item for k in ["id", "type", "text"]): raise ValueError(f"要素 {i} に必須キー (id, type, text) が不足しています。")
                if item.get("type") != "summary": raise ValueError(f"要素 {i} の type が 'summary' ではありません。")
                validated_list.append(item)
            print("バックエンド: 要約生成完了 (JSONパース・検証成功)")
            return validated_list
        except (json.JSONDecodeError, ValueError) as e:
            print(f"バックエンド: 要約生成失敗 (JSONパースまたは検証エラー: {e})")
            print("LLM応答 (生文字列):", response_str)
            return None
    else:
        print("バックエンド: 要約生成失敗 (API呼び出し失敗またはJSON抽出失敗)")
        return None

def generate_quiz(transcript):
    """
    文字起こしテキストをクイズ生成LLM (DeepSeek API via OpenAI Lib) に送信する。
    成功したら質問のリスト (Pythonオブジェクト) を、失敗したらNoneを返す。
    """
    print("バックエンド: クイズ生成開始 (DeepSeek API via OpenAI Lib)")
    # プロンプトは前回と同じ
    prompt = f"""
以下の会議の文字起こしテキストを分析し、内容の理解度を確認するための3択クイズを3問生成してください。

**出力形式の厳格な指示:**
結果は必ずJSON形式のリストとして出力してください。他のテキスト（例: 説明文、前置きなど）は一切含めないでください。
リストの各要素はJSONオブジェクト（辞書）で、以下のキーを含みます:
- "id": 文字列。 "q1", "q2", "q3" のように連番を振ってください。
- "type": 文字列。 必ず "question" としてください。
- "text": 文字列。 質問文を入れてください。
- "options": 文字列のリスト。 必ず3つの選択肢を格納してください。
- "answer": 文字列。 3つの選択肢の中から正解となるものを指定してください。

**出力形式の例 (この例自身は出力に含めないでください):**
[
  {{"id": "q1", "type": "question", "text": "質問文1?", "options": ["選択肢A", "選択肢B", "選択肢C"], "answer": "正解の選択肢"}},
  {{"id": "q2", "type": "question", "text": "質問文2?", "options": ["選択肢X", "選択肢Y", "選択肢Z"], "answer": "正解の選択肢"}},
  {{"id": "q3", "type": "question", "text": "質問文3?", "options": ["選択肢1", "選択肢2", "選択肢3"], "answer": "正解の選択肢"}}
]

**文字起こしテキスト:**
---
{transcript}
---

上記の指示に従い、JSON形式のクイズリストのみを出力してください。説明や前置きは不要です。
"""
    # 呼び出す関数を変更
    response_str = call_deepseek_via_openai(prompt, temperature=0.3, max_tokens=1500)

    # 以降のJSONパースと検証ロジックは前回と同じ
    if response_str:
        try:
            quiz_list = json.loads(response_str)
            if not isinstance(quiz_list, list): raise ValueError("応答がリスト形式ではありません。")
            if not quiz_list: raise ValueError("応答リストが空です。")
            validated_list = []
            required_keys = ["id", "type", "text", "options", "answer"]
            for i, item in enumerate(quiz_list):
                if not isinstance(item, dict): raise ValueError(f"要素 {i} が辞書形式ではありません。")
                if not all(k in item for k in required_keys): raise ValueError(f"要素 {i} に必須キー ({', '.join(required_keys)}) が不足しています。")
                if item.get("type") != "question": raise ValueError(f"要素 {i} の type が 'question' ではありません。")
                options = item.get("options")
                if not isinstance(options, list) or len(options) != 3: raise ValueError(f"要素 {i} の 'options' が3つの要素を持つリストではありません。")
                if not all(isinstance(opt, str) for opt in options): raise ValueError(f"要素 {i} の 'options' の要素がすべて文字列ではありません。")
                answer = item.get("answer")
                if not isinstance(answer, str) or answer not in options: raise ValueError(f"要素 {i} の 'answer' が options 内の有効な文字列ではありません。")
                validated_list.append(item)
            print("バックエンド: クイズ生成完了 (JSONパース・検証成功)")
            return validated_list
        except (json.JSONDecodeError, ValueError) as e:
            print(f"バックエンド: クイズ生成失敗 (JSONパースまたは検証エラー: {e})")
            print("LLM応答 (生文字列):", response_str)
            return None
    else:
        print("バックエンド: クイズ生成失敗 (API呼び出し失敗またはJSON抽出失敗)")
        return None



# --- ルーティング (HTMLページ表示) ---

@app.route('/')
@app.route('/input')
def input_page():
    """入力画面を表示"""
    return render_template('input.html')

@app.route('/history')
def history_page():
    """履歴画面を表示"""
    # TODO: データベースなどから実際の履歴を取得してテンプレートに渡す
    dummy_history = [
        {'id': 'content_abc', 'type': 'quiz', 'title': '面白い動画のクイズ', 'date': '2023/10/27 10:00'},
        {'id': 'content_def', 'type': 'summary', 'title': '学習動画の要約', 'date': '2023/10/26 18:30'},
        {'id': 'content_ghi', 'type': 'quiz', 'title': 'プレゼン練習用クイズ', 'date': '2023/10/25 09:15'},
    ]
    return render_template('history.html', history_items=dummy_history) # ダミーデータを渡す

@app.route('/learning')
def learning_page():
    """学習画面を表示"""
    content_id = request.args.get('id') # URLパラメータ (?id=...) を取得
    title = request.args.get('title', '学習コンテンツ') # タイトルも取得 (任意)
    # content_id に基づいてデータを取得する想定
    print(f"学習画面リクエスト: id={content_id}, title={title}")
    # この時点ではHTMLを返すだけ。データはJSがAPIを叩いて取得する
    return render_template('learning.html', content_id=content_id, title=title)

@app.route('/settings')
def settings_page():
    """設定画面を表示"""
    return render_template('settings.html')

# --- APIエンドポイント ---

@app.route('/api/generate', methods=['POST'])
def generate_content():
    """YouTube URLを受け取り、要約とクイズを生成して返すAPI"""
    if not request.is_json:
        return jsonify({"success": False, "message": "リクエスト形式が不正です (JSONではありません)"}), 400

    data = request.get_json()
    youtube_url = data.get('url')

    if not youtube_url:
        return jsonify({"success": False, "message": "URLが指定されていません"}), 400

    print(f"API: /api/generate 受信 - URL: {youtube_url}")

    # --- バックエンド処理の実行 ---
    try:
        # 1. 音声抽出 (ダミー)
        audio_path = download_and_extract_audio(youtube_url)
        if not audio_path:
            raise ValueError("音声ファイルの抽出に失敗しました。")

        # TODO: 抽出した音声ファイルをどこかに保存・管理する必要がある

        # 2. 文字起こし (ダミー)
        transcript = transcribe_audio(audio_path)
        if not transcript:
             raise ValueError("文字起こしに失敗しました。")

        # TODO: 文字起こし結果を保存・管理する必要があるかもしれない

        # 3. 要約生成 (ダミー)
        summary_items = generate_summary(transcript)
        if not summary_items:
            raise ValueError("要約の生成に失敗しました。")

        # 4. クイズ生成 (ダミー)
        question_items = generate_quiz(transcript)
        if not question_items:
             raise ValueError("クイズの生成に失敗しました。")

        # --- 成功レスポンスの作成 ---
        # 実際には生成したコンテンツに一意のIDを付与し、DBなどに保存する
        content_id = f"content_{random.randint(10000, 99999)}"
        video_title = f"動画タイトル ({youtube_url[-5:]})" # ダミータイトル

        response_data = {
            "id": content_id,
            "title": video_title,
            "thumbnail": f"https://via.placeholder.com/300x169.png?text=Video+{content_id[-3:]}", # ダミーサムネイル
            "summary": summary_items,
            "questions": question_items
        }

        print(f"API: /api/generate 成功 - Content ID: {content_id}")
        return jsonify({"success": True, "data": response_data}), 200

    except Exception as e:
        print(f"API: /api/generate エラー - {e}")
        return jsonify({"success": False, "message": f"処理中にエラーが発生しました: {str(e)}"}), 500


@app.route('/api/learning/<content_id>', methods=['GET'])
def get_learning_content(content_id):
    """指定されたIDの学習コンテンツ（要約とクイズ）を返すAPI"""
    print(f"API: /api/learning/{content_id} 受信")

    # --- ここで content_id に基づいてDBなどからデータを取得 ---
    # (今回はダミーデータを返す)
    try:
        # ダミーデータ生成ロジック (generate_content と似たものを返す)
        time.sleep(random.uniform(0.5, 1.5)) # DBアクセスを模倣

        # IDに基づいて少し内容を変えるダミー
        is_quiz_type = 'quiz' in content_id or random.random() > 0.5
        title_suffix = content_id.split('_')[-1] if '_' in content_id else content_id

        dummy_summary = [
            {"id": f"s_{title_suffix}_1", "type": "summary", "text": f"({title_suffix}) 要約スライド その1"},
            {"id": f"s_{title_suffix}_2", "type": "summary", "text": f"({title_suffix}) 要約スライド その2"}
        ] if not is_quiz_type else [] # クイズタイプなら要約は空にするダミー

        dummy_questions = [
            {"id": f"q_{title_suffix}_1", "type": "question", "text": f"({title_suffix}) の質問1ですか？", "options": ["はい", "いいえ"], "answer": "はい"},
            {"id": f"q_{title_suffix}_2", "type": "question", "text": f"({title_suffix}) の質問2です。", "options": ["選択肢X", "選択肢Y"], "answer": "選択肢Y"}
        ] if is_quiz_type else [] # 要約タイプならクイズは空にするダミー

        # learningItemsの形式で結合
        items = dummy_summary + dummy_questions
        if not items: # もし両方空ならエラーメッセージ
             items = [{"id": "info_empty", "type": "info", "text": f"コンテンツID '{content_id}' のデータが見つかりませんでした。"}]


        response_data = {
            "title": f"取得したタイトル {title_suffix}",
            "items": items,
            "totalItems": len(items) # itemsの合計数を返す
        }

        # 10%くらいの確率で失敗させるダミー
        if random.random() < 0.1:
             raise FileNotFoundError("指定されたコンテンツデータが見つかりませんでした (ダミーエラー)。")

        print(f"API: /api/learning/{content_id} 成功")
        return jsonify({"success": True, "data": response_data}), 200

    except Exception as e:
         print(f"API: /api/learning/{content_id} エラー - {e}")
         # Not Foundエラーなどを返すのが適切かもしれない
         return jsonify({"success": False, "message": f"コンテンツ取得エラー: {str(e)}"}), 404 # or 500


# --- アプリケーションの実行 ---
if __name__ == '__main__':
    # デバッグモードで実行 (開発時のみ True にする)
    # 実際の運用では Gunicorn などのWSGIサーバーを使用する
    app.run(debug=True, host='0.0.0.0', port=7860)