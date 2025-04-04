console.log("Script loaded.");

// --- input.html ---
/**
 * 入力画面のフォーム送信時の処理
 */
function handleGenerateSubmit() {
    const urlInput = document.getElementById('youtube-url');
    const button = document.getElementById('generate-button');
    const buttonText = button.querySelector('.button-text');
    const buttonIcon = button.querySelector('.icon');
    const spinner = button.querySelector('.loading-spinner');
    const errorMessage = document.getElementById('error-message');
    const placeholder = document.getElementById('image-placeholder');
    const url = urlInput.value.trim();

    errorMessage.textContent = ''; // エラーメッセージをクリア
    if (!url) {
        errorMessage.textContent = 'YouTubeリンクを入力してください。';
        urlInput.focus(); // 入力欄にフォーカス
        return false; // フォーム送信を中止
    }
    // 簡単なURLチェック (より厳密なチェック推奨)
    if (!url.includes('youtube.com/') && !url.includes('youtu.be/')) {
        errorMessage.textContent = '有効なYouTubeリンクの形式ではありません。';
        urlInput.focus();
        return false;
    }

    // ローディング表示開始
    button.disabled = true;
    urlInput.disabled = true; // 入力欄も無効化
    buttonText.textContent = '生成中...';
    buttonIcon.style.display = 'none';
    spinner.style.display = 'inline-block';
    placeholder.innerHTML = '<div class="loading-spinner" style="display: inline-block; border-color: rgba(0,0,0,0.1); border-top-color: #555;"></div><span style="margin-left: 10px; color: #555;">処理中...</span>'; // プレースホルダーも更新

    console.log('Generating for:', url);

    // --- バックエンドAPIを呼び出す ---
    fetch('/api/generate', { // Flaskの /api/generate エンドポイントを呼び出す
        method: 'POST',
        body: JSON.stringify({ url: url }), // url をJSONで送信
        headers: {'Content-Type': 'application/json'}
    })
    .then(response => {
        // レスポンスが成功(2xx)でない場合、エラーとして処理
        if (!response.ok) {
            // エラーレスポンスの内容を読み取ってエラーオブジェクトを生成
            // response.json() は非同期なので Promise を返す
            return response.json().then(errData => {
                // APIが返したメッセージを使う。なければHTTPステータスベースのメッセージ
                throw new Error(errData.message || `サーバーエラーが発生しました (HTTP ${response.status})`);
            }).catch(jsonError => {
                // JSONパース自体が失敗した場合 (レスポンスがJSONでないなど)
                 console.error("Failed to parse error response JSON:", jsonError);
                 throw new Error(`サーバーエラーが発生しました (HTTP ${response.status})`);
            });
        }
        return response.json(); // 成功したらJSONをパース
    })
    .then(result => {
        // APIが成功(200 OK)を返しても、ビジネスロジック上の失敗がありうる (success: false)
        if (result.success && result.data) {
            console.log('Generation successful:', result.data);
            // サムネイル表示
            placeholder.innerHTML = `<img src="${result.data.thumbnail}" alt="動画サムネイル">`;

            // 生成されたコンテンツIDとタイトルをパラメータに付けて学習画面へ遷移
            // encodeURIComponentでURLセーフな文字列に変換
            const contentId = encodeURIComponent(result.data.id);
            const title = encodeURIComponent(result.data.title);
            // 少し待ってから遷移（サムネイル表示のため）
            setTimeout(() => {
                 window.location.href = `/learning?id=${contentId}&title=${title}`; // Flaskのルーティングに合わせる
            }, 500);
            // 画面遷移するので、この後のローディング解除は不要

        } else {
            // APIが成功(200 OK)でも success: false を返した場合や、dataがない場合
            throw new Error(result.message || 'APIからの応答が不正です。');
        }
    })
    .catch(error => {
        console.error('Generation failed:', error);
        errorMessage.textContent = error.message || '生成中に不明なエラーが発生しました。';
         // ローディング解除 (エラー時)
         button.disabled = false;
         urlInput.disabled = false;
         buttonText.textContent = '生成する';
         buttonIcon.style.display = 'inline-block';
         spinner.style.display = 'none';
         placeholder.innerHTML = '<span>(イメージ表示エリア)</span>'; // エラー時は元に戻す
    });
    // .finally ブロックは fetch が完了したらいつでも実行されるが、
    // 成功時の画面遷移があるので、ここではローディング解除は catch 内で行う

    return false; // 通常のフォーム送信は行わない (preventDefaultと同じ効果)
}


// --- history.html ---
// TODO: 履歴データをAPIから取得して表示する関数 (必要なら実装)
/*
document.addEventListener('DOMContentLoaded', fetchHistory);

function fetchHistory() {
    const listElement = document.getElementById('history-list');
    if (!listElement) return;

    listElement.innerHTML = '<li>履歴を読み込み中...</li>'; // ローディング表示

    fetch('/api/history') // 仮のAPIエンドポイント
        .then(response => {
            if (!response.ok) throw new Error('履歴の取得に失敗しました');
            return response.json();
        })
        .then(result => {
            listElement.innerHTML = ''; // ローディング表示をクリア
            if (result.success && result.data && result.data.length > 0) {
                result.data.forEach(item => {
                    const listItem = document.createElement('li');
                    listItem.className = 'list-item';
                    const link = document.createElement('a');
                    link.href = `/learning?id=${encodeURIComponent(item.id)}&title=${encodeURIComponent(item.title)}`;
                    link.className = 'list-item-button';
                    link.innerHTML = `
                        <div class="list-item-content">
                            <span class="list-item-icon">${item.type === 'quiz' ? '📊' : '📄'}</span>
                            <div class="list-item-text">
                                <h3>${item.title}</h3>
                                <p>${item.date}</p>
                            </div>
                        </div>
                        <span class="list-arrow">></span>
                    `;
                    listItem.appendChild(link);
                    listElement.appendChild(listItem);
                });
            } else {
                 listElement.innerHTML = '<li>履歴はありません。</li>';
            }
        })
        .catch(error => {
            console.error('Failed to fetch history:', error);
            listElement.innerHTML = `<li>履歴の読み込みに失敗しました: ${error.message}</li>`;
        });
}
*/


// --- learning.html ---
let currentLearningIndex = 0; // 現在表示しているアイテムのインデックス
let learningItems = [];       // 学習アイテム（要約やクイズ）の配列
let currentAnswer = '';       // 現在表示中のクイズの正解（答え合わせ用）
let isAnswerRevealed = false; // 答えが表示されているかどうかのフラグ

/**
 * learning.html が読み込まれたときに実行される初期化関数
 */
function initializeLearningScreen() {
    console.log("Initializing Learning Screen");
    const params = new URLSearchParams(window.location.search);
    const contentId = params.get('id');
    let title = params.get('title'); // inputから渡された仮タイトル
    const titleElement = document.getElementById('learning-title');
    const cardText = document.getElementById('card-text');
    const pageInfo = document.getElementById('page-info');
    const prevButton = document.getElementById('prev-button');
    const nextButton = document.getElementById('next-button');
    const modeIndicator = document.getElementById('mode-indicator');
    const tapToShow = document.getElementById('tap-to-show');
    const optionsArea = document.getElementById('options-area');

    // ボタンを一旦無効化
    prevButton.disabled = true;
    nextButton.disabled = true;

    // まずは仮タイトル表示とローディング表示
    if (title) {
        titleElement.textContent = `学習セット: ${decodeURIComponent(title)}`;
    } else if (contentId) {
        titleElement.textContent = `学習セット: ${contentId}`;
    } else {
         titleElement.textContent = '学習コンテンツ';
    }
    cardText.textContent = 'コンテンツを読み込み中...';
    pageInfo.textContent = '... / ...';
    modeIndicator.textContent = '';
    tapToShow.style.display = 'none';
    optionsArea.innerHTML = '';

    if (!contentId) {
        cardText.textContent = 'コンテンツIDが指定されていません。';
        pageInfo.textContent = '0 / 0';
        console.error("コンテンツIDがURLパラメータにありません。");
        // エラー表示を維持して終了
        return;
    }

    // --- contentIdに基づいてバックエンドから学習データを取得 ---
    fetch(`/api/learning/${contentId}`) // Flaskの /api/learning/<content_id> エンドポイントを叩く
        .then(response => {
             if (!response.ok) {
                 // エラーレスポンス処理
                 return response.json().then(errData => {
                     throw new Error(errData.message || `データ取得エラー (HTTP ${response.status})`);
                 }).catch(jsonError => {
                     throw new Error(`データ取得エラー (HTTP ${response.status})`);
                 });
             }
             return response.json();
         })
        .then(result => {
            if (result.success && result.data && result.data.items) {
                console.log("Learning data loaded:", result.data);
                learningItems = result.data.items; // 取得したデータをグローバル変数にセット
                // APIから取得した正式なタイトルで更新
                if (result.data.title) {
                    titleElement.textContent = `学習セット: ${result.data.title}`;
                }

                if (learningItems.length > 0) {
                    currentLearningIndex = 0;
                    displayLearningItem(); // 最初のアイテムを表示
                } else {
                    // データはあるが中身が空の場合
                    cardText.textContent = 'このコンテンツには表示するアイテムがありません。';
                    pageInfo.textContent = '0 / 0';
                    modeIndicator.textContent = '情報';
                }
            } else {
                // success: false または data/items がない場合
                throw new Error(result.message || '学習データの形式が不正です。');
            }
        })
        .catch(error => {
            console.error('Failed to load learning data:', error);
            cardText.textContent = `エラー: ${error.message}`;
            pageInfo.textContent = '0 / 0';
            modeIndicator.textContent = 'エラー';
            // ボタンは無効のまま
        });
}

/**
 * learningItems 配列の currentLearningIndex 番目のアイテムを画面に表示する
 */
function displayLearningItem() {
    const card = document.getElementById('learning-card');
    const cardText = document.getElementById('card-text');
    const answerText = document.getElementById('answer-text');
    const tapToShow = document.getElementById('tap-to-show');
    const modeIndicator = document.getElementById('mode-indicator');
    const optionsArea = document.getElementById('options-area');
    const pageInfo = document.getElementById('page-info');
    const prevButton = document.getElementById('prev-button');
    const nextButton = document.getElementById('next-button');

    isAnswerRevealed = false; // 新しいアイテム表示時は答えを隠す状態にリセット

    if (learningItems.length === 0 || currentLearningIndex < 0 || currentLearningIndex >= learningItems.length) {
        console.error("表示する学習アイテムが見つかりません。", currentLearningIndex, learningItems.length);
        cardText.textContent = 'エラー：アイテムを表示できません。';
        pageInfo.textContent = '0 / 0';
        prevButton.disabled = true;
        nextButton.disabled = true;
        return;
    }

    const item = learningItems[currentLearningIndex];

    // テキスト表示 (改行コード \n を <br> に変換して表示する場合)
    // cardText.innerHTML = item.text.replace(/\\n/g, '<br>');
    // テキスト表示 (改行コードをそのまま表示する場合 - CSSで white-space: pre-wrap が必要)
    cardText.textContent = item.text.replace(/\\n/g, '\n');

    answerText.style.display = 'none'; // 最初は答えを隠す
    optionsArea.innerHTML = '';      // 選択肢エリアをクリア
    card.onclick = null;             // カードクリックイベントを一旦解除
    tapToShow.onclick = null;        // タップテキストのクリックも解除
    tapToShow.style.display = 'none';

    if (item.type === 'question') {
        modeIndicator.textContent = 'クイズモード';
        card.style.cursor = 'pointer';
        tapToShow.style.display = 'block';
        card.onclick = revealAnswer;      // カードクリックで答え表示
        tapToShow.onclick = revealAnswer; // タップテキストクリックでも答え表示
        currentAnswer = item.answer;      // 答えを保持
        answerText.textContent = `答え: ${item.answer || '(未設定)'}`; // 答え表示用テキスト設定

        // 選択肢ボタンを作成
        if (item.options && Array.isArray(item.options) && item.options.length > 0) {
            item.options.forEach((option, index) => {
                const button = document.createElement('button');
                button.className = 'option-button'; // style.cssでスタイル定義が必要
                // インラインスタイルで基本的なスタイルを設定（CSSで定義推奨）
                 button.style.cssText = `
                    display: block; width: 100%; text-align: left;
                    padding: 10px 15px; margin-bottom: 8px; font-size: 15px;
                    border: 1px solid #ccc; border-radius: 8px; background-color: #fff;
                    cursor: pointer; transition: background-color 0.2s, border-color 0.2s, font-weight 0.2s;`;
                button.textContent = `${String.fromCharCode(65 + index)}: ${option}`; // 例: A: 選択肢A
                button.onclick = () => checkAnswer(option, button); // クリック時の処理を設定
                optionsArea.appendChild(button);
            });
        } else {
             optionsArea.innerHTML = '<p style="color: #888; font-size: 14px;">(選択肢がありません)</p>';
        }

    } else if (item.type === 'summary') {
        modeIndicator.textContent = '要約モード';
        card.style.cursor = 'default';
        optionsArea.innerHTML = ''; // 選択肢不要
        currentAnswer = '';         // 答えなし
    } else { // infoなど、想定外のタイプ
        modeIndicator.textContent = '情報';
        card.style.cursor = 'default';
        optionsArea.innerHTML = '';
        currentAnswer = '';
    }

    // ページネーション更新
    pageInfo.textContent = `${currentLearningIndex + 1} / ${learningItems.length}`;
    prevButton.disabled = (currentLearningIndex === 0);
    nextButton.disabled = (currentLearningIndex === learningItems.length - 1);
}

/**
 * クイズの答えを表示する関数
 */
function revealAnswer() {
    const item = learningItems[currentLearningIndex];
    // クイズタイプのアイテムで、まだ答えが表示されていない場合のみ実行
    if (item.type === 'question' && !isAnswerRevealed) {
        const answerText = document.getElementById('answer-text');
        const optionsArea = document.getElementById('options-area');
        const tapToShow = document.getElementById('tap-to-show');

        answerText.style.display = 'block'; // 答えを表示
        tapToShow.style.display = 'none'; // 「タップして表示」を隠す
        isAnswerRevealed = true;          // 答え表示済みフラグを立てる

        // 全ての選択肢ボタンの状態を更新して正解・不正解を示す
        const buttons = optionsArea.querySelectorAll('.option-button');
        buttons.forEach(btn => {
            // ボタンテキストから選択肢内容を抽出 (例: "A: はい" -> "はい")
            const optionText = btn.textContent.substring(btn.textContent.indexOf(':') + 1).trim();
             btn.disabled = true; // 答え表示後はボタンを無効化
             btn.style.cursor = 'default';

            if (optionText === currentAnswer) {
                // 正解のボタンのスタイル
                btn.style.backgroundColor = '#d6eaff'; // 明るい青背景
                btn.style.borderColor = '#007bff';     // 青い枠線
                btn.style.fontWeight = 'bold';       // 太字
            } else {
                 // 不正解のボタンのスタイル
                 btn.style.backgroundColor = '#f8f8f8'; // グレー背景
                 btn.style.color = '#888';           // グレー文字
                 btn.style.borderColor = '#eee';
            }
        });
    }
}

/**
 * クイズの選択肢がクリックされたときの処理 (答え表示前に選択状態を示す)
 */
function checkAnswer(selectedOption, buttonElement) {
    // 答えが表示されていない場合のみ実行
    if (!isAnswerRevealed) {
        console.log('Selected:', selectedOption);
        const optionsArea = document.getElementById('options-area');
        // 他のボタンの選択状態を解除
        optionsArea.querySelectorAll('.option-button').forEach(btn => {
            btn.style.fontWeight = 'normal';
            btn.style.backgroundColor = '#fff'; // 背景をリセット
            btn.style.borderColor = '#ccc';     // 枠線もリセット
        });
         // 選択したボタンを強調
        buttonElement.style.fontWeight = 'bold';
        buttonElement.style.backgroundColor = '#e9e9e9'; // 少しグレーに
        buttonElement.style.borderColor = '#aaa';

        // (任意) 選択肢を選んだら自動的に答えを表示する場合
        // revealAnswer();
    }
}


/**
 * 次の学習アイテムへ移動する
 */
function goToNext() {
    if (currentLearningIndex < learningItems.length - 1) {
        currentLearningIndex++;
        displayLearningItem();
    }
}

/**
 * 前の学習アイテムへ移動する
 */
function goToPrev() {
    if (currentLearningIndex > 0) {
        currentLearningIndex--;
        displayLearningItem();
    }
}

// --- settings.html ---
/**
 * 設定画面のトグルスイッチが変更されたときの処理
 */
function handleToggleChange(checkbox, settingType) {
    console.log(`${settingType} toggled:`, checkbox.checked);
    // TODO: 設定値を保存する処理 (例: LocalStorage)
    try {
         localStorage.setItem(`setting_${settingType}`, checkbox.checked);
         console.log(`Setting ${settingType} saved to localStorage.`);
    } catch (e) {
        console.error("Failed to save setting to localStorage:", e);
        // localStorageが使えない環境向けのフォールバックなど
    }
}

/**
 * ログアウトボタンがクリックされたときの処理
 */
function handleLogout() {
    if (confirm('ログアウトしますか？ (現在の学習状態は保存されません)')) {
        console.log('Logging out...');
        // TODO: 実際のログアウト処理 (Cookie削除、サーバーへの通知など)
        // localStorageから関連データを削除する例
        // localStorage.removeItem('userToken');
        // localStorage.removeItem('setting_push');
        // localStorage.removeItem('setting_dark');
        // ...

        // その後、ログイン画面や初期画面に遷移
        window.location.href = '/input'; // 初期画面に戻る例 (Flaskのルートに合わせる)
    }
}

// --- Common ---
/**
 * メニューボタンがクリックされたときの処理（ダミー）
 */
function openMenu() {
    alert('サイドメニュー表示（未実装）\n\n実際のアプリではここにメニュー開閉のロジックが入ります。');
    // 例:
    // const sidebar = document.getElementById('sidebar');
    // if (sidebar) {
    //    sidebar.classList.toggle('open');
    // }
}

// --- 初期化処理 ---
// learning.html の場合のみ、DOMContentLoadedで初期化関数を呼び出す
if (window.location.pathname.includes('/learning')) {
    document.addEventListener('DOMContentLoaded', initializeLearningScreen);
}

// 設定画面の場合、LocalStorageから設定を読み込む例
/*
if (window.location.pathname.includes('/settings')) {
    document.addEventListener('DOMContentLoaded', () => {
        try {
            const pushToggle = document.querySelector('input[onchange*="push"]');
            if (pushToggle) {
                const savedPush = localStorage.getItem('setting_push');
                // 保存された値が 'true' または null (未設定=デフォルトtrueとする場合) ならチェック
                pushToggle.checked = (savedPush === 'true' || savedPush === null);
            }

            const darkToggle = document.querySelector('input[onchange*="dark"]');
             if (darkToggle) {
                 const savedDark = localStorage.getItem('setting_dark');
                 // 保存された値が 'true' の場合のみチェック
                 darkToggle.checked = (savedDark === 'true');
                 // TODO: ダークモードの実際のスタイル切り替え処理
                 // document.body.classList.toggle('dark-mode', darkToggle.checked);
             }
        } catch (e) {
             console.error("Failed to load settings from localStorage:", e);
        }
    });
}
*/