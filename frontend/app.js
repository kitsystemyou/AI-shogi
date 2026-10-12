/**
 * AI & JEV 将棋アリーナ フロントエンドスクリプト (app.js)
 */

// 駒文字マッピング
const PIECE_MAP = {
  // 先手 (大文字)
  'P': { name: '歩', promoted: false, color: 'sente' },
  'L': { name: '香', promoted: false, color: 'sente' },
  'N': { name: '桂', promoted: false, color: 'sente' },
  'S': { name: '銀', promoted: false, color: 'sente' },
  'G': { name: '金', promoted: false, color: 'sente' },
  'B': { name: '角', promoted: false, color: 'sente' },
  'R': { name: '飛', promoted: false, color: 'sente' },
  'K': { name: '玉', promoted: false, color: 'sente' },
  '+P': { name: 'と', promoted: true, color: 'sente' },
  '+L': { name: '杏', promoted: true, color: 'sente' },
  '+N': { name: '圭', promoted: true, color: 'sente' },
  '+S': { name: '全', promoted: true, color: 'sente' },
  '+B': { name: '馬', promoted: true, color: 'sente' },
  '+R': { name: '竜', promoted: true, color: 'sente' },

  // 後手 (小文字)
  'p': { name: '歩', promoted: false, color: 'gote' },
  'l': { name: '香', promoted: false, color: 'gote' },
  'n': { name: '桂', promoted: false, color: 'gote' },
  's': { name: '銀', promoted: false, color: 'gote' },
  'g': { name: '金', promoted: false, color: 'gote' },
  'b': { name: '角', promoted: false, color: 'gote' },
  'r': { name: '飛', promoted: false, color: 'gote' },
  'k': { name: '王', promoted: false, color: 'gote' },
  '+p': { name: 'と', promoted: true, color: 'gote' },
  '+l': { name: '杏', promoted: true, color: 'gote' },
  '+n': { name: '圭', promoted: true, color: 'gote' },
  '+s': { name: '全', promoted: true, color: 'gote' },
  '+b': { name: '馬', promoted: true, color: 'gote' },
  '+r': { name: '竜', promoted: true, color: 'gote' },
};

// 初期SFEN
const INITIAL_SFEN = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1";

// アプリケーション状態
const state = {
  currentMatchId: null,
  eventSource: null,
  currentMoves: [],
  currentStepIndex: 0,
  isPlaying: false,
  playTimer: null,
  currentSfen: INITIAL_SFEN,
  lastMoveUsi: null,
  sentePlayer: "JEV",
  gotePlayer: "Gemini 3.8 Flash",
  isLive: false,
};

// DOM要素
const elements = {
  arenaView: document.getElementById('arena-view'),
  historyView: document.getElementById('history-view'),
  tabArenaBtn: document.getElementById('tab-arena-btn'),
  tabHistoryBtn: document.getElementById('tab-history-btn'),
  openConfigBtn: document.getElementById('open-config-btn'),
  configModal: document.getElementById('config-modal'),
  closeConfigBtn: document.getElementById('close-config-btn'),
  cancelConfigBtn: document.getElementById('cancel-config-btn'),
  saveConfigBtn: document.getElementById('save-config-btn'),
  senteSelect: document.getElementById('sente-select'),
  goteSelect: document.getElementById('gote-select'),
  startMatchBtn: document.getElementById('start-match-btn'),
  stopMatchBtn: document.getElementById('stop-match-btn'),
  shogiGrid: document.getElementById('shogi-grid'),
  boardSenteName: document.getElementById('board-sente-name'),
  boardGoteName: document.getElementById('board-gote-name'),
  boardSenteHand: document.getElementById('board-sente-hand'),
  boardGoteHand: document.getElementById('board-gote-hand'),
  currentTurnText: document.getElementById('current-turn-text'),
  moveCountText: document.getElementById('move-count-text'),
  gameStatusMessage: document.getElementById('game-status-message'),
  movesListContainer: document.getElementById('moves-list-container'),
  aiLogContent: document.getElementById('ai-log-content'),
  logModelName: document.getElementById('log-model-name'),
  copyKifBtn: document.getElementById('copy-kif-btn'),
  historyTableBody: document.getElementById('history-table-body'),
  refreshHistoryBtn: document.getElementById('refresh-history-btn'),
  senteStatusBadge: document.getElementById('sente-status-badge'),
  goteStatusBadge: document.getElementById('gote-status-badge'),

  // ナビゲーション
  navFirst: document.getElementById('nav-first'),
  navPrev: document.getElementById('nav-prev'),
  navPlay: document.getElementById('nav-play'),
  navNext: document.getElementById('nav-next'),
  navLast: document.getElementById('nav-last'),
  navCurrentStep: document.getElementById('nav-current-step'),
  navTotalSteps: document.getElementById('nav-total-steps'),
};

// 初期化処理
async function init() {
  initBoardGrid();
  setupEventListeners();
  renderBoard(INITIAL_SFEN);
  await checkConfigStatus();
}

// 81マスの盤面DOM初期化
function initBoardGrid() {
  elements.shogiGrid.innerHTML = '';
  // 9筋から1筋 (x=0..8 -> 筋9..1), 1段から9段 (y=0..8 -> 段一..九)
  // 描画順: 1段目(9一〜1一), 2段目(9二〜1二), ...
  for (let rank = 1; rank <= 9; rank++) {
    for (let file = 9; file >= 1; file--) {
      const cell = document.createElement('div');
      cell.className = 'shogi-cell';
      cell.dataset.file = file;
      cell.dataset.rank = rank;
      cell.id = `cell-${file}-${rank}`;
      elements.shogiGrid.appendChild(cell);
    }
  }
}

// SFENのパースと盤面描画
function renderBoard(sfen, lastMoveUsi = null) {
  state.currentSfen = sfen;
  const parts = sfen.split(' ');
  const boardPart = parts[0];
  const turnPart = parts[1] || 'b';
  const handPart = parts[2] || '-';

  // 1. 全マスのクリア
  const cells = elements.shogiGrid.querySelectorAll('.shogi-cell');
  cells.forEach(c => {
    c.innerHTML = '';
    c.classList.remove('last-move-dest', 'last-move-src');
  });

  // 2. 盤面駒配置の展開
  const rows = boardPart.split('/');
  for (let rIndex = 0; rIndex < rows.length; rIndex++) {
    const rank = rIndex + 1;
    const rowStr = rows[rIndex];
    let file = 9;

    let i = 0;
    while (i < rowStr.length) {
      const ch = rowStr[i];
      if (ch >= '1' && ch <= '9') {
        file -= parseInt(ch, 10);
        i++;
      } else {
        let pieceKey = ch;
        if (ch === '+') {
          pieceKey = '+' + rowStr[i + 1];
          i += 2;
        } else {
          i++;
        }

        const cell = document.getElementById(`cell-${file}-${rank}`);
        if (cell && PIECE_MAP[pieceKey]) {
          const pieceInfo = PIECE_MAP[pieceKey];
          const pieceDiv = document.createElement('div');
          pieceDiv.className = `piece ${pieceInfo.color} ${pieceInfo.promoted ? 'promoted' : ''}`;
          pieceDiv.textContent = pieceInfo.name;
          cell.appendChild(pieceDiv);
        }
        file--;
      }
    }
  }

  // 3. 直前の着手をハイライト
  if (lastMoveUsi) {
    highlightMove(lastMoveUsi);
  }

  // 4. 持ち駒の描画
  renderHands(handPart);

  // 5. 手番インジケータ
  if (turnPart === 'b') {
    elements.currentTurnText.textContent = "先手 (▲) 手番";
  } else {
    elements.currentTurnText.textContent = "後手 (△) 手番";
  }
}

// 直前の指し手ハイライト
function highlightMove(usi) {
  if (!usi) return;
  // 例: 7g7f または P*5e
  if (usi.includes('*')) {
    // 駒打ち
    const dest = usi.slice(2); // 例: 5b
    const destFile = parseInt(dest[0], 10);
    const destRank = dest.charCodeAt(1) - 96;
    const destCell = document.getElementById(`cell-${destFile}-${destRank}`);
    if (destCell) destCell.classList.add('last-move-dest');
  } else if (usi.length >= 4) {
    const srcFile = parseInt(usi[0], 10);
    const srcRank = usi.charCodeAt(1) - 96;
    const destFile = parseInt(usi[2], 10);
    const destRank = usi.charCodeAt(3) - 96;

    const srcCell = document.getElementById(`cell-${srcFile}-${srcRank}`);
    const destCell = document.getElementById(`cell-${destFile}-${destRank}`);

    if (srcCell) srcCell.classList.add('last-move-src');
    if (destCell) destCell.classList.add('last-move-dest');
  }
}

// 持ち駒の描画
function renderHands(handPart) {
  elements.boardSenteHand.innerHTML = '';
  elements.boardGoteHand.innerHTML = '';

  if (!handPart || handPart === '-') {
    elements.boardSenteHand.textContent = 'なし';
    elements.boardGoteHand.textContent = 'なし';
    return;
  }

  const senteCounts = {};
  const goteCounts = {};

  let count = 1;
  for (let i = 0; i < handPart.length; i++) {
    const ch = handPart[i];
    if (ch >= '0' && ch <= '9') {
      let numStr = ch;
      while (i + 1 < handPart.length && handPart[i + 1] >= '0' && handPart[i + 1] <= '9') {
        numStr += handPart[i + 1];
        i++;
      }
      count = parseInt(numStr, 10);
    } else {
      if (ch === ch.toUpperCase()) {
        senteCounts[ch] = count;
      } else {
        goteCounts[ch] = count;
      }
      count = 1;
    }
  }

  // 描画ヘルパー
  const order = ['R', 'B', 'G', 'S', 'N', 'L', 'P'];
  const kanji = { 'R': '飛', 'B': '角', 'G': '金', 'S': '銀', 'N': '桂', 'L': '香', 'P': '歩' };

  let senteHas = false;
  for (const k of order) {
    if (senteCounts[k]) {
      senteHas = true;
      const span = document.createElement('span');
      span.className = 'hand-badge';
      span.textContent = `${kanji[k]}${senteCounts[k] > 1 ? senteCounts[k] : ''}`;
      elements.boardSenteHand.appendChild(span);
    }
  }
  if (!senteHas) elements.boardSenteHand.textContent = 'なし';

  let goteHas = false;
  for (const k of order) {
    const lower = k.toLowerCase();
    if (goteCounts[lower]) {
      goteHas = true;
      const span = document.createElement('span');
      span.className = 'hand-badge';
      span.textContent = `${kanji[k]}${goteCounts[lower] > 1 ? goteCounts[lower] : ''}`;
      elements.boardGoteHand.appendChild(span);
    }
  }
  if (!goteHas) elements.boardGoteHand.textContent = 'なし';
}

// 対戦開始処理
async function startMatch() {
  const sente = elements.senteSelect.value;
  const gote = elements.goteSelect.value;

  elements.startMatchBtn.disabled = true;
  elements.startMatchBtn.classList.add('opacity-50');

  try {
    const res = await fetch('/api/matches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sente_player: sente, gote_player: gote })
    });

    if (!res.ok) {
      const err = await res.json();
      alert(`対局開始に失敗しました: ${err.detail || 'エラー'}`);
      return;
    }

    const data = await res.json();
    state.currentMatchId = data.match_id;
    state.sentePlayer = sente;
    state.gotePlayer = gote;
    state.currentMoves = [];
    state.currentStepIndex = 0;
    state.isLive = true;

    // UI初期化
    elements.boardSenteName.textContent = sente;
    elements.boardGoteName.textContent = gote;
    elements.gameStatusMessage.textContent = "対局中...";
    elements.movesListContainer.innerHTML = '';
    elements.stopMatchBtn.classList.remove('hidden');

    renderBoard(INITIAL_SFEN);
    updateNavButtons();

    // SSE接続の開始
    connectSSE(data.match_id);

  } catch (err) {
    console.error(err);
    alert('対局開始エラーが発生しました');
  } finally {
    elements.startMatchBtn.disabled = false;
    elements.startMatchBtn.classList.remove('opacity-50');
  }
}

// 対戦中断処理
async function stopMatch() {
  if (!state.currentMatchId) return;
  try {
    await fetch(`/api/matches/${state.currentMatchId}/stop`, { method: 'POST' });
    elements.gameStatusMessage.textContent = "対局中断をリクエストしました";
  } catch (err) {
    console.error(err);
  }
}

// SSE (Server-Sent Events) 接続
function connectSSE(matchId) {
  if (state.eventSource) {
    state.eventSource.close();
  }

  const es = new EventSource(`/api/matches/${matchId}/events`);
  state.eventSource = es;

  es.onmessage = (event) => {
    try {
      const raw = JSON.parse(event.data);
      handleServerEvent(raw);
    } catch (e) {
      console.warn("SSE parse error", e, event.data);
    }
  };

  es.onerror = (e) => {
    console.warn("SSE connection closed or error", e);
  };
}

// サーバーイベントの処理
function handleServerEvent(payload) {
  const event = payload.event;
  const data = payload.data;

  if (event === "thinking") {
    const turnStr = data.turn === "sente" ? "先手 (▲)" : "後手 (△)";
    elements.currentTurnText.textContent = `${turnStr} 思考中...`;
    elements.logModelName.textContent = data.player_name;
    elements.aiLogContent.innerHTML = `<div class="text-amber-400 animate-pulse">【${data.player_name}】が指し手を思考中... (${data.move_number}手目)</div>`;
  } else if (event === "move") {
    const move = data.move;
    state.currentMoves.push(move);
    state.currentStepIndex = state.currentMoves.length;

    // 最新局面の描画
    renderBoard(move.sfen_after, move.usi);

    // 棋譜リストに追加
    addMoveToKifList(move, state.currentMoves.length);

    // 思考ログ更新
    elements.logModelName.textContent = `${move.model_name} (${move.player === 'sente' ? '▲' : '△'})`;
    elements.aiLogContent.innerHTML = formatAILog(move);

    elements.moveCountText.textContent = `${move.move_number}手目`;
    updateNavButtons();
  } else if (event === "finished") {
    elements.gameStatusMessage.textContent = `対局終了: ${data.reason}`;
    elements.stopMatchBtn.classList.add('hidden');
    state.isLive = false;
    if (state.eventSource) state.eventSource.close();
  } else if (event === "aborted") {
    elements.gameStatusMessage.textContent = `対局中断: ${data.reason}`;
    elements.stopMatchBtn.classList.add('hidden');
    state.isLive = false;
    if (state.eventSource) state.eventSource.close();
  } else if (event === "error") {
    elements.gameStatusMessage.textContent = `エラー終了: ${data.error}`;
    elements.stopMatchBtn.classList.add('hidden');
    state.isLive = false;
    if (state.eventSource) state.eventSource.close();
  }
}

// 棋譜行の追加
function addMoveToKifList(move, index) {
  const row = document.createElement('div');
  row.className = 'kif-row';
  row.dataset.index = index;

  const isSente = move.player === 'sente';
  const mark = isSente ? '▲' : '△';
  const markColor = isSente ? 'text-red-400' : 'text-blue-400';

  row.innerHTML = `
    <div class="flex items-center gap-2">
      <span class="text-slate-500 w-8">${move.move_number}.</span>
      <span class="${markColor} font-bold">${mark} ${move.kif_text}</span>
      <span class="text-slate-400 text-[11px]">(${move.usi})</span>
    </div>
    <div class="flex items-center gap-2 text-[10px] text-slate-500">
      <span>${move.model_name}</span>
      <span>${move.time_spent_ms}ms</span>
    </div>
  `;

  row.addEventListener('click', () => {
    jumpToStep(index);
  });

  elements.movesListContainer.appendChild(row);
  elements.movesListContainer.scrollTop = elements.movesListContainer.scrollHeight;

  highlightActiveKifRow(index);
}

function highlightActiveKifRow(index) {
  const rows = elements.movesListContainer.querySelectorAll('.kif-row');
  rows.forEach(r => {
    if (parseInt(r.dataset.index, 10) === index) {
      r.classList.add('active');
    } else {
      r.classList.remove('active');
    }
  });
}

function formatAILog(move) {
  let out = `<div><strong>指し手:</strong> ${move.kif_text} (<code>${move.usi}</code>)</div>`;
  out += `<div><strong>消費時間:</strong> ${move.time_spent_ms} ms</div>`;

  if (move.ai_response) {
    try {
      const parsed = typeof move.ai_response === 'string' ? JSON.parse(move.ai_response) : move.ai_response;
      if (parsed.reason) {
        out += `<div class="mt-2 text-amber-200"><strong>思考理由:</strong> ${parsed.reason}</div>`;
      }
      if (parsed.raw) {
        out += `<details class="mt-2 cursor-pointer text-slate-400 text-[11px]"><summary class="hover:text-slate-200">API 生レスポンス (JSON)</summary><pre class="mt-1 bg-slate-900 p-2 rounded overflow-x-auto text-[10px]">${JSON.stringify(parsed.raw, null, 2)}</pre></details>`;
      }
    } catch {
      out += `<div class="mt-2 text-slate-300">${move.ai_response}</div>`;
    }
  }
  return out;
}

// 局面ジャンプ (棋譜再現)
function jumpToStep(index) {
  state.currentStepIndex = index;
  if (index === 0) {
    renderBoard(INITIAL_SFEN);
    elements.moveCountText.textContent = "0手目 (初期局面)";
    elements.logModelName.textContent = "--";
    elements.aiLogContent.innerHTML = '<span class="text-slate-500">初期局面です</span>';
  } else {
    const move = state.currentMoves[index - 1];
    renderBoard(move.sfen_after, move.usi);
    elements.moveCountText.textContent = `${move.move_number}手目`;
    elements.logModelName.textContent = `${move.model_name} (${move.player === 'sente' ? '▲' : '△'})`;
    elements.aiLogContent.innerHTML = formatAILog(move);
  }
  highlightActiveKifRow(index);
  updateNavButtons();
}

function updateNavButtons() {
  const total = state.currentMoves.length;
  elements.navTotalSteps.textContent = total;
  elements.navCurrentStep.textContent = state.currentStepIndex;

  elements.navFirst.disabled = state.currentStepIndex <= 0;
  elements.navPrev.disabled = state.currentStepIndex <= 0;
  elements.navNext.disabled = state.currentStepIndex >= total;
  elements.navLast.disabled = state.currentStepIndex >= total;
}

// 自動再生
function togglePlay() {
  if (state.isPlaying) {
    stopPlay();
  } else {
    startPlay();
  }
}

function startPlay() {
  state.isPlaying = true;
  document.getElementById('play-icon').setAttribute('data-lucide', 'pause');
  lucide.createIcons();

  state.playTimer = setInterval(() => {
    if (state.currentStepIndex < state.currentMoves.length) {
      jumpToStep(state.currentStepIndex + 1);
    } else {
      stopPlay();
    }
  }, 1000);
}

function stopPlay() {
  state.isPlaying = false;
  clearInterval(state.playTimer);
  document.getElementById('play-icon').setAttribute('data-lucide', 'play');
  lucide.createIcons();
}

// 対戦履歴一覧読み込み
async function loadHistory() {
  elements.historyTableBody.innerHTML = '<tr><td colspan="8" class="text-center py-8 text-slate-500">履歴を読み込み中...</td></tr>';
  try {
    const res = await fetch('/api/matches');
    const data = await res.json();
    const matches = data.matches || [];

    if (matches.length === 0) {
      elements.historyTableBody.innerHTML = '<tr><td colspan="8" class="text-center py-8 text-slate-500">対戦履歴はまだありません</td></tr>';
      return;
    }

    elements.historyTableBody.innerHTML = '';
    matches.forEach(m => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-800/40 transition-colors';

      let winnerText = '対局中';
      let winnerClass = 'text-amber-400';
      if (m.status === 'finished') {
        if (m.winner === 'sente') {
          winnerText = `先手勝 (${m.sente_player})`;
          winnerClass = 'text-red-400 font-bold';
        } else if (m.winner === 'gote') {
          winnerText = `後手勝 (${m.gote_player})`;
          winnerClass = 'text-blue-400 font-bold';
        } else {
          winnerText = '引き分け';
          winnerClass = 'text-slate-300';
        }
      } else if (m.status === 'aborted') {
        winnerText = '中断';
        winnerClass = 'text-slate-500';
      } else if (m.status === 'error') {
        winnerText = 'エラー終了';
        winnerClass = 'text-red-500';
      }

      const dateStr = new Date(m.created_at).toLocaleString('ja-JP');

      tr.innerHTML = `
        <td class="px-4 py-3 font-mono text-xs">#${m.id}</td>
        <td class="px-4 py-3 text-xs text-slate-400">${dateStr}</td>
        <td class="px-4 py-3 font-semibold text-red-300">▲ ${m.sente_player}</td>
        <td class="px-4 py-3 font-semibold text-blue-300">△ ${m.gote_player}</td>
        <td class="px-4 py-3 ${winnerClass}">${winnerText}</td>
        <td class="px-4 py-3 font-mono">${m.total_moves} 手</td>
        <td class="px-4 py-3 text-xs text-slate-400">${m.finish_reason || '--'}</td>
        <td class="px-4 py-3 text-right">
          ${m.status === 'aborted' ? `
            <button class="resume-match-btn px-3 py-1 bg-green-700/80 hover:bg-green-700 text-white rounded text-xs transition-colors mr-2" data-id="${m.id}">
              再開
            </button>
          ` : ''}
          <button class="view-match-btn px-3 py-1 bg-amber-600/80 hover:bg-amber-600 text-white rounded text-xs transition-colors" data-id="${m.id}">
            棋譜再生
          </button>
        </td>
      `;

      const resumeButton = tr.querySelector('.resume-match-btn');
      if (resumeButton) {
        resumeButton.addEventListener('click', () => resumeMatch(m.id, resumeButton));
      }
      tr.querySelector('.view-match-btn').addEventListener('click', () => {
        loadMatchDetail(m.id);
      });

      elements.historyTableBody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
    elements.historyTableBody.innerHTML = '<tr><td colspan="8" class="text-center py-8 text-red-400">履歴の取得に失敗しました</td></tr>';
  }
}

async function resumeMatch(matchId, button) {
  button.disabled = true;
  button.textContent = '再開中...';
  try {
    const res = await fetch(`/api/matches/${matchId}/resume`, { method: 'POST' });
    if (!res.ok) {
      const error = await res.json();
      alert(`対局を再開できませんでした: ${error.detail || 'エラー'}`);
      return;
    }
    await loadMatchDetail(matchId);
  } catch (err) {
    console.error(err);
    alert('対局再開エラーが発生しました');
  } finally {
    button.disabled = false;
    button.textContent = '再開';
  }
}

// 過去の対局を棋譜ビューアにロード
async function loadMatchDetail(matchId) {
  try {
    const res = await fetch(`/api/matches/${matchId}`);
    if (!res.ok) return;
    const data = await res.json();
    const match = data.match;
    const moves = data.moves || [];

    // アリーナタブに切り替え
    switchTab('arena');

    state.currentMatchId = match.id;
    state.sentePlayer = match.sente_player;
    state.gotePlayer = match.gote_player;
    state.currentMoves = moves;
    state.currentStepIndex = 0;
    state.isLive = data.is_running;

    elements.boardSenteName.textContent = match.sente_player;
    elements.boardGoteName.textContent = match.gote_player;
    elements.movesListContainer.innerHTML = '';

    if (match.status === 'finished') {
      elements.gameStatusMessage.textContent = `対局終了 (${match.winner === 'sente' ? '先手勝ち' : match.winner === 'gote' ? '後手勝ち' : '引分'}): ${match.finish_reason || ''}`;
      elements.stopMatchBtn.classList.add('hidden');
    } else if (match.status === 'aborted') {
      const abortMessages = {
        api_rate_limited: 'LLM API のレート制限により対局を中断しました',
        api_payment_required: 'LLM API が HTTP 402 を返したため対局を中断しました',
      };
      elements.gameStatusMessage.textContent = abortMessages[match.finish_reason] || '対局は中断されました';
      elements.stopMatchBtn.classList.add('hidden');
    } else if (data.is_running) {
      elements.gameStatusMessage.textContent = "対局中...";
      elements.stopMatchBtn.classList.remove('hidden');
      connectSSE(match.id);
    }

    moves.forEach((m, idx) => {
      addMoveToKifList(m, idx + 1);
    });

    if (moves.length > 0) {
      jumpToStep(moves.length);
    } else {
      renderBoard(INITIAL_SFEN);
      updateNavButtons();
    }
  } catch (err) {
    console.error(err);
  }
}

// 棋譜テキストのクリップボードコピー
function copyKifu() {
  if (state.currentMoves.length === 0) {
    alert('コピーする棋譜がありません');
    return;
  }
  let txt = `# AI & JEV 将棋アリーナ 棋譜\n`;
  txt += `先手: ${state.sentePlayer}\n`;
  txt += `後手: ${state.gotePlayer}\n`;
  txt += `手数: ${state.currentMoves.length}\n`;
  txt += `---------------------------------\n`;

  state.currentMoves.forEach(m => {
    const p = m.player === 'sente' ? '▲' : '△';
    txt += `${m.move_number} ${p}${m.kif_text} (${m.usi})\n`;
  });

  navigator.clipboard.writeText(txt).then(() => {
    alert('棋譜をクリップボードにコピーしました！');
  }).catch(() => {
    alert('コピーに失敗しました');
  });
}

// API設定ステータス取得
async function checkConfigStatus() {
  try {
    const res = await fetch('/api/config');
    const cfg = await res.json();

    updateBadge(elements.senteStatusBadge, elements.senteSelect.value, cfg);
    updateBadge(elements.goteStatusBadge, elements.goteSelect.value, cfg);

    document.getElementById('cfg-openai-status').textContent = cfg.openai.has_key ? '設定済み ✓' : '未設定 ✕';
    document.getElementById('cfg-openai-status').className = cfg.openai.has_key ? 'text-[11px] text-green-400 font-semibold' : 'text-[11px] text-red-400';
    document.getElementById('cfg-openai-model').value = cfg.openai.model;

    document.getElementById('cfg-gemini-status').textContent = cfg.gemini.has_key ? '設定済み ✓' : '未設定 ✕';
    document.getElementById('cfg-gemini-status').className = cfg.gemini.has_key ? 'text-[11px] text-green-400 font-semibold' : 'text-[11px] text-red-400';
    document.getElementById('cfg-gemini-model').value = cfg.gemini.model;

    document.getElementById('cfg-anthropic-status').textContent = cfg.anthropic.has_key ? '設定済み ✓' : '未設定 ✕';
    document.getElementById('cfg-anthropic-status').className = cfg.anthropic.has_key ? 'text-[11px] text-green-400 font-semibold' : 'text-[11px] text-red-400';
    document.getElementById('cfg-anthropic-model').value = cfg.anthropic.model;

    document.getElementById('cfg-jev-status').textContent = cfg.jev.has_key ? '設定済み ✓' : '未設定 ✕';
    document.getElementById('cfg-jev-status').className = cfg.jev.has_key ? 'text-[11px] text-green-400 font-semibold' : 'text-[11px] text-red-400';
    document.getElementById('cfg-jev-endpoint').value = cfg.jev.endpoint;
  } catch (err) {
    console.error(err);
  }
}

function updateBadge(badge, modelName, cfg) {
  let hasKey = false;
  if (modelName.includes('GPT')) hasKey = cfg.openai?.has_key;
  else if (modelName.includes('Gemini')) hasKey = cfg.gemini?.has_key;
  else if (modelName.includes('Claude')) hasKey = cfg.anthropic?.has_key;
  else if (modelName.includes('JEV')) hasKey = cfg.jev?.has_key;

  if (hasKey) {
    badge.textContent = 'APIキー設定済 ✓';
    badge.className = 'text-xs text-green-400 font-medium';
  } else {
    badge.textContent = 'APIキー未設定 ✕';
    badge.className = 'text-xs text-amber-400 font-medium';
  }
}

// タブ切り替え
function switchTab(tab) {
  if (tab === 'arena') {
    elements.arenaView.classList.remove('hidden');
    elements.historyView.classList.add('hidden');
    elements.tabArenaBtn.className = 'px-4 py-2 rounded-lg text-sm font-medium transition-colors bg-amber-600 text-white flex items-center gap-1.5 shadow-sm';
    elements.tabHistoryBtn.className = 'px-4 py-2 rounded-lg text-sm font-medium transition-colors text-slate-300 hover:text-white hover:bg-slate-800 flex items-center gap-1.5';
  } else {
    elements.arenaView.classList.add('hidden');
    elements.historyView.classList.remove('hidden');
    elements.tabHistoryBtn.className = 'px-4 py-2 rounded-lg text-sm font-medium transition-colors bg-amber-600 text-white flex items-center gap-1.5 shadow-sm';
    elements.tabArenaBtn.className = 'px-4 py-2 rounded-lg text-sm font-medium transition-colors text-slate-300 hover:text-white hover:bg-slate-800 flex items-center gap-1.5';
    loadHistory();
  }
}

// イベントリスナー設定
function setupEventListeners() {
  elements.tabArenaBtn.addEventListener('click', () => switchTab('arena'));
  elements.tabHistoryBtn.addEventListener('click', () => switchTab('history'));

  elements.senteSelect.addEventListener('change', checkConfigStatus);
  elements.goteSelect.addEventListener('change', checkConfigStatus);

  elements.startMatchBtn.addEventListener('click', startMatch);
  elements.stopMatchBtn.addEventListener('click', stopMatch);

  // 局面ナビゲーション
  elements.navFirst.addEventListener('click', () => jumpToStep(0));
  elements.navPrev.addEventListener('click', () => jumpToStep(Math.max(0, state.currentStepIndex - 1)));
  elements.navNext.addEventListener('click', () => jumpToStep(Math.min(state.currentMoves.length, state.currentStepIndex + 1)));
  elements.navLast.addEventListener('click', () => jumpToStep(state.currentMoves.length));
  elements.navPlay.addEventListener('click', togglePlay);

  elements.copyKifBtn.addEventListener('click', copyKifu);
  elements.refreshHistoryBtn.addEventListener('click', loadHistory);

  // モーダル
  elements.openConfigBtn.addEventListener('click', () => elements.configModal.classList.remove('hidden'));
  elements.closeConfigBtn.addEventListener('click', () => elements.configModal.classList.add('hidden'));
  elements.cancelConfigBtn.addEventListener('click', () => elements.configModal.classList.add('hidden'));

  elements.saveConfigBtn.addEventListener('click', async () => {
    const payload = {};
    const openaiKey = document.getElementById('cfg-openai-key').value.trim();
    const openaiModel = document.getElementById('cfg-openai-model').value.trim();
    if (openaiKey) payload.openai_api_key = openaiKey;
    if (openaiModel) payload.openai_model = openaiModel;

    const geminiKey = document.getElementById('cfg-gemini-key').value.trim();
    const geminiModel = document.getElementById('cfg-gemini-model').value.trim();
    if (geminiKey) payload.gemini_api_key = geminiKey;
    if (geminiModel) payload.gemini_model = geminiModel;

    const anthropicKey = document.getElementById('cfg-anthropic-key').value.trim();
    const anthropicModel = document.getElementById('cfg-anthropic-model').value.trim();
    if (anthropicKey) payload.anthropic_api_key = anthropicKey;
    if (anthropicModel) payload.anthropic_model = anthropicModel;

    const jevKey = document.getElementById('cfg-jev-key').value.trim();
    const jevEndpoint = document.getElementById('cfg-jev-endpoint').value.trim();
    if (jevKey) payload.jev_api_key = jevKey;
    if (jevEndpoint) payload.jev_endpoint = jevEndpoint;

    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    elements.configModal.classList.add('hidden');
    await checkConfigStatus();
    alert('設定を更新いたしました！');
  });
}

document.addEventListener('DOMContentLoaded', init);
