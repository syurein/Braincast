// static/script.js

"use strict"; // より厳格なエラーチェック

// --- グローバル変数 ---
let learningData = null;    // 学習データ (learning.html用)
let currentItemIndex = 0;   // 現在表示中のアイテムインデックス (learning.html用)
let currentMode = 'quiz';   // 現在のモード 'quiz' or 'summary' (learning.html用)

// --- 共通関数 ---

/**
 * 指定されたURLに遷移します。
 * @param {string} url - 遷移先のURL
 */
function navigateTo(url) {
    window.location.href = url;
}

/**
 * メニューボタンがクリックされたときの処理（仮）
 * TODO: 実際のメニューUIを実装する
 */
function openMenu() {
    console.log("Menu button clicked. Implement menu display logic here.");
    // 例: サイドバーメニューを表示する、モーダルを表示するなど
    alert("メニュー機能は未実装です。\nフッターのナビゲーションを使用してください。");
}

/**
 * ローディングスピナーを表示/非表示します。
 * @param {boolean} show - trueで表示、falseで非表示
 */
function toggleLoading(show) {
    const spinner = document.querySelector('.loading-spinner'); // input.html用
    const buttonText = document.querySelector('.button-text'); // input.html用
    const generateButton = document.getElementById('generate-button'); // input.html用

    if (spinner && buttonText && generateButton) {
        spinner.style.display = show ? 'inline-block' : 'none';
        buttonText.textContent = show ? '生成中...' : '生成する';
        generateButton.disabled = show;
    }
    // learning.html 用のローディング表示/非表示も必要に応じて追加
    const loadingCard = document.getElementById('loading-card-indicator'); // 仮のID
    if (loadingCard) {
        loadingCard.style.display = show ? 'block' : 'none';
    }
}

/**
 * エラーメッセージを表示します。
 * @param {string} message - 表示するエラーメッセージ
 * @param {string} elementId - メッセージを表示する要素のID (デフォルト: 'error-message')
 */
function displayErrorMessage(message, elementId = 'error-message') {
    const errorElement = document.getElementById(elementId);
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.display = message ? 'block' : 'none';
    }
}

// --- 画面遷移用関数 ---
function goToInput() {
    navigateTo('/'); // input.html はルートパスに割り当てる想定
}

function goToHistory() {
    navigateTo('/history');
}

function goToSettings() {
    navigateTo('/settings');
}

function goToLearning(contentId) {
    if (contentId) {
        navigateTo(`/learning?id=${encodeURIComponent(contentId)}`);
    } else {
        console.error('goToLearning requires a content ID.');
        alert('学習コンテンツIDが見つかりません。');
    }
}


// --- input.html 用の処理 ---

/**
 * 生成フォームの送信処理
 */
async function handleGenerateSubmit() {
    const urlInput = document.getElementById('youtube-url');
    const youtubeUrl = urlInput.value.trim();
    displayErrorMessage(''); // 前のエラーメッセージをクリア

    if (!youtubeUrl) {
        displayErrorMessage('YouTubeリンクを入力してください。');
        return false; // prevent default form submission
    }

    // 簡単なURL形式チェック（より厳密なチェックも可能）
    if (!youtubeUrl.includes('youtube.com/') && !youtubeUrl.includes('youtu.be/')) {
         displayErrorMessage('有効なYouTubeリンクを入力してください。');
         return false;
    }


    toggleLoading(true); // ローディング開始

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: youtubeUrl }),
        });

        const result = await response.json();

        if (response.ok && result.success && result.data && result.data.id) {
            // 成功したら学習画面へ遷移
            alert('生成に成功しました！学習画面に移動します。');
            goToLearning(result.data.id);
        } else {
            // 失敗したらエラーメッセージ表示
            console.error('Generation failed:', result);
            displayErrorMessage(result.message || '生成中にエラーが発生しました。');
        }

    } catch (error) {
        console.error('Error during generation request:', error);
        displayErrorMessage('通信エラーが発生しました。');
    } finally {
        toggleLoading(false); // ローディング終了
    }

    return false; // prevent default form submission
}


// --- learning.html 用の処理 ---

/**
 * learning.html の初期化
 */
async function initializeLearningScreen() {
    console.log('Initializing Learning Screen...');
    const params = new URLSearchParams(window.location.search);
    const contentId = params.get('id');
    const loadingIndicator = document.getElementById('mode-indicator'); // 仮にモード表示部を使う
    const cardElement = document.getElementById('learning-card');
    const paginationElement = document.querySelector('.pagination');

    if (!contentId) {
        displayLearningError('コンテンツIDが指定されていません。');
        return;
    }
    console.log('Content ID:', contentId);

    // ローディング表示（簡易版）
    if (loadingIndicator) loadingIndicator.textContent = '読み込み中...';
    if (cardElement) cardElement.style.opacity = '0.5'; // 少し薄くする
    if (paginationElement) paginationElement.style.display = 'none';


    try {
        const response = await fetch(`/api/learning/${contentId}`);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ message: `HTTPエラー: ${response.status}` }));
            throw new Error(errorData.message || `サーバーからのデータ取得に失敗しました (${response.status})`);
        }

        const result = await response.json();
        console.log('Fetched data:', result);

        if (result.success && result.data) {
            learningData = result.data; // グローバル変数に格納
            if (!learningData.items || learningData.items.length === 0) {
                 throw new Error('学習データが空です。');
            }
            // タイトルを設定
            const titleElement = document.getElementById('learning-title');
            if (titleElement) {
                titleElement.textContent = learningData.title || '学習コンテンツ';
            }

            // 最初のアイテムを表示
            currentItemIndex = 0;
            displayCurrentItem();
             if (paginationElement) paginationElement.style.display = 'flex'; // ページネーション表示

        } else {
            throw new Error(result.message || '学習データの読み込みに失敗しました。');
        }

    } catch (error) {
        console.error('Error initializing learning screen:', error);
        displayLearningError(`読み込みエラー: ${error.message}`);
    } finally {
        // ローディング表示終了（簡易版）
        if (cardElement) cardElement.style.opacity = '1';
        // mode-indicatorはdisplayCurrentItemで更新される
    }
}

/**
 * 現在の学習アイテムをカードに表示
 */
function displayCurrentItem() {
    if (!learningData || !learningData.items || currentItemIndex < 0 || currentItemIndex >= learningData.items.length) {
        console.error('Invalid learning data or index');
        displayLearningError('学習データを表示できません。');
        return;
    }

    const item = learningData.items[currentItemIndex];
    const cardTextElement = document.getElementById('card-text');
    const answerTextElement = document.getElementById('answer-text');
    const tapToShowElement = document.getElementById('tap-to-show');
    const optionsArea = document.getElementById('options-area');
    const modeIndicator = document.getElementById('mode-indicator');

    // リセット
    cardTextElement.innerHTML = '';
    answerTextElement.style.display = 'none';
    tapToShowElement.style.display = 'none';
    optionsArea.innerHTML = '';
    optionsArea.style.display = 'none';

    if (item.type === 'question') {
        currentMode = 'quiz';
        modeIndicator.textContent = 'クイズモード';
        cardTextElement.textContent = item.text; // 質問文
        answerTextElement.textContent = `答え: ${item.answer}`; // 答えを事前に設定（非表示）
        tapToShowElement.style.display = 'block'; // タップして表示を表示

        // 選択肢ボタンを生成（解答チェックはここではしない）
        if (item.options && Array.isArray(item.options)) {
            optionsArea.style.display = 'block';
            item.options.forEach(option => {
                const button = document.createElement('button');
                button.classList.add('option-button');
                button.textContent = option;
                // ★★★ 選択肢クリック時の動作を変更: 正誤判定ではなく解答表示 ★★★
                button.onclick = revealAnswer; // どのボタンを押しても解答表示
                optionsArea.appendChild(button);
            });
        }

    } else if (item.type === 'summary') {
        currentMode = 'summary';
        modeIndicator.textContent = '要約モード';
        cardTextElement.innerHTML = item.text.replace(/\n/g, '<br>'); // 要約文（改行対応）

        // 要約モードでは答えも選択肢も不要
    } else {
        console.warn('Unknown item type:', item.type);
        cardTextElement.textContent = `[不明なデータタイプ: ${item.type}] ${item.text || ''}`;
        modeIndicator.textContent = '不明モード';
    }

    updatePagination();
}

/**
 * クイズの解答を表示する
 */
function revealAnswer() {
    // クイズモードの場合のみ動作
    if (currentMode === 'quiz') {
        const answerTextElement = document.getElementById('answer-text');
        const tapToShowElement = document.getElementById('tap-to-show');
        const optionsArea = document.getElementById('options-area');

        if (answerTextElement) {
            answerTextElement.style.display = 'block'; // 答えを表示
        }
        if (tapToShowElement) {
            tapToShowElement.style.display = 'none'; // 「タップして表示」を隠す
        }

        // 選択肢ボタンを正解・不正解で色付け＆無効化
        if (optionsArea && learningData && learningData.items[currentItemIndex]) {
             const correctAnswer = learningData.items[currentItemIndex].answer;
             const buttons = optionsArea.getElementsByTagName('button');
             for (let btn of buttons) {
                btn.disabled = true; // ボタンを無効化
                if (btn.textContent === correctAnswer) {
                    btn.classList.add('correct'); // 正解スタイル
                } else {
                    btn.classList.add('disabled'); // 不正解または他の選択肢スタイル
                }
                // クリックイベントを削除（任意）
                btn.onclick = null;
            }
        }
    }
}


/**
 * 次のアイテムへ移動
 */
function goToNext() {
    if (learningData && currentItemIndex < learningData.items.length - 1) {
        currentItemIndex++;
        displayCurrentItem();
    }
}

/**
 * 前のアイテムへ移動
 */
function goToPrev() {
    if (learningData && currentItemIndex > 0) {
        currentItemIndex--;
        displayCurrentItem();
    }
}

/**
 * ページネーション表示を更新
 */
function updatePagination() {
    const pageInfo = document.getElementById('page-info');
    const prevButton = document.getElementById('prev-button');
    const nextButton = document.getElementById('next-button');

    if (pageInfo && prevButton && nextButton && learningData && learningData.items) {
        const totalItems = learningData.items.length;
        pageInfo.textContent = `${currentItemIndex + 1} / ${totalItems}`;
        prevButton.disabled = currentItemIndex === 0;
        nextButton.disabled = currentItemIndex === totalItems - 1;
    }
}

/**
 * learning.html でエラーを表示
 */
function displayLearningError(message) {
    const cardElement = document.getElementById('learning-card');
    const titleElement = document.getElementById('learning-title');
    const paginationElement = document.querySelector('.pagination');
    const optionsArea = document.getElementById('options-area');
    const modeIndicator = document.getElementById('mode-indicator');
    const tapToShow = document.getElementById('tap-to-show');

    if (titleElement) titleElement.textContent = 'エラー';
    if (cardElement) cardElement.innerHTML = `<p class="main-text" style="color: red; text-align: center;">${message}</p>`;
    if (paginationElement) paginationElement.style.display = 'none';
    if (optionsArea) optionsArea.style.display = 'none';
    if (modeIndicator) modeIndicator.style.display = 'none';
    if (tapToShow) tapToShow.style.display = 'none';
}


// --- settings.html 用の処理 ---

/**
 * トグルスイッチの変更ハンドラ
 */
function handleToggleChange(checkbox, type) {
    console.log(`Toggle changed for ${type}: ${checkbox.checked}`);
    if (type === 'dark') {
        document.body.classList.toggle('dark-mode', checkbox.checked);
        try {
            localStorage.setItem('darkModeEnabled', checkbox.checked);
        } catch (e) {
            console.warn('Could not save dark mode preference to localStorage.');
        }
    }
    // 他のトグル（例: プッシュ通知）の処理もここに追加
}

/**
 * ログアウトボタンの処理
 */
function handleLogout() {
    console.log("Logout clicked");
    // TODO: 実際のログアウト処理（API呼び出し、セッションクリアなど）
    alert("ログアウト機能は未実装です。");
    // 必要であればログイン画面などに遷移
    // navigateTo('/login');
}

/**
 * ダークモード設定を読み込んで適用する
 */
function applyDarkModePreference() {
     try {
        const darkModeEnabled = localStorage.getItem('darkModeEnabled') === 'true';
        document.body.classList.toggle('dark-mode', darkModeEnabled);
        // 設定画面のトグルスイッチの状態も合わせる
        const toggle = document.querySelector('input[onchange*="handleToggleChange"][onchange*="dark"]');
        if (toggle) {
            toggle.checked = darkModeEnabled;
        }
    } catch (e) {
        console.warn('Could not load dark mode preference from localStorage.');
    }
}


// --- ページの初期化処理 ---
document.addEventListener('DOMContentLoaded', () => {
    const pathname = window.location.pathname;

    applyDarkModePreference(); // 全ページでダークモード設定を適用

    if (pathname === '/' || pathname === '/input') {
        // input.html の初期化（特に不要かもしれないが、フォームイベントリスナーなど）
        const form = document.getElementById('generate-form');
        if (form) {
            form.addEventListener('submit', (event) => {
                 event.preventDefault(); // デフォルトの送信をキャンセル
                 handleGenerateSubmit();
            });
        }
    } else if (pathname === '/learning') {
        initializeLearningScreen();
    } else if (pathname === '/history') {
        // history.html の初期化（動的にリストを生成する場合など）
        // このサンプルでは静的なので特に不要
    } else if (pathname === '/settings') {
        // settings.html の初期化（ダークモードの適用は applyDarkModePreference で実施済み）
    }

    // フッターナビゲーションのアクティブ状態設定（任意）
    updateFooterNavActiveState(pathname);
});


/**
 * フッターナビゲーションのアクティブ状態を更新
 */
 function updateFooterNavActiveState(pathname) {
    const footerNav = document.querySelector('.footer-nav');
    if (!footerNav) return;

    const buttons = footerNav.querySelectorAll('button');
    buttons.forEach(button => {
        button.classList.remove('active'); // Reset all
        const onclickAttr = button.getAttribute('onclick');
        if (onclickAttr) {
            if ((pathname === '/' || pathname === '/input') && onclickAttr.includes('goToInput')) {
                button.classList.add('active');
            } else if (pathname === '/history' && onclickAttr.includes('goToHistory')) {
                button.classList.add('active');
            } else if (pathname === '/settings' && onclickAttr.includes('goToSettings')) {
                button.classList.add('active');
            }
        }
    });
}


// デバッグ用に一部関数をグローバルスコープに公開（開発中のみ推奨）
window.debug = {
    navigateTo,
    goToInput,
    goToHistory,
    goToSettings,
    goToLearning,
    openMenu,
    handleGenerateSubmit,
    initializeLearningScreen,
    revealAnswer,
    goToNext,
    goToPrev,
    handleToggleChange,
    handleLogout
};