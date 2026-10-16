package com.tabletopgame.game;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

/**
 * 一局 UNO 的完整状态机（纯逻辑，不依赖服务端 API，可独立单测）。
 * <p>
 * 流程：{@link #PHASE_DEALER_DRAW 定庄} → {@link #PHASE_PLAYING 对局} → {@link #PHASE_FINISHED 结束}。
 *
 * <h2>定庄（官方规则）</h2>
 * 每人抽一张牌；数字牌按数字比大小，功能牌与野牌一律算 0；数字最大者为本局庄家；
 * 多人并列最大则全部重新抽牌；定完庄后把抽的牌放回牌堆重新洗牌发牌。庄家无手牌优势（同样 7 张）。
 * <p>
 * 先手 = 庄家**左手边**（顺时针下一位），庄家自己不是先手。
 *
 * <h2>轮次</h2>
 * 座位号 0..n-1 按顺时针排列，{@code direction = +1} 表示顺时针推进。
 * <ul>
 *   <li>跳过：下家被跳过；</li>
 *   <li>反转：方向取反；**2 人局反转等同跳过**（即自己再出一张）；</li>
 *   <li>+2 / +4：下家摸对应张数并被跳过（本实现**不叠加反击**，一次只结算一张）；</li>
 *   <li>Wild：出牌时由出牌人指定颜色。</li>
 * </ul>
 *
 * <h2>回合内动作</h2>
 * <ol>
 *   <li>正常出牌（可自愿摸牌）；</li>
 *   <li>摸牌后，若摸到的牌可出 → 可「出牌」；</li>
 *   <li>摸牌后，无论能否出都可以「跳过」结束回合。</li>
 * </ol>
 * 摸牌后只允许打出**刚摸到的那张**（官方行为）。
 */
public final class UnoGame {

    /** 定庄阶段。 */
    public static final int PHASE_DEALER_DRAW = 0;
    /** 对局阶段。 */
    public static final int PHASE_PLAYING = 1;
    /** 已结束（有人出完牌，或牌堆耗尽无法继续）。 */
    public static final int PHASE_FINISHED = 2;

    /** {@link #drawForDealer(int)} 返回：本次抽牌成功，还有人没抽。 */
    public static final int DRAW_OK = 0;
    /** {@link #drawForDealer(int)} 返回：并列最大，全部重抽。 */
    public static final int DRAW_TIE_REDRAW = 1;
    /** {@link #drawForDealer(int)} 返回：庄家已确定。 */
    public static final int DRAW_DEALER_DECIDED = 2;

    private final int players;
    private final Random random;

    private final List<List<Integer>> hands = new ArrayList<>();
    /** 摸牌堆：末位为堆顶。 */
    private final List<Integer> drawPile = new ArrayList<>();
    /** 弃牌堆：末位为顶牌（当前有效牌）。 */
    private final List<Integer> discard = new ArrayList<>();

    private int phase = PHASE_DEALER_DRAW;
    private int currentSeat;
    private int direction = 1;
    /** 当前有效颜色（0..3）；-1 表示等待选色。 */
    private int activeColor = -1;
    private int dealerSeat = -1;
    private int winnerSeat = -1;
    private int dealerDrawRound = 1;

    /** 定庄阶段每人抽到的牌（-1 = 还没抽）。 */
    private final int[] dealerDraw;

    /** 起始牌是 Wild 时，先手需先选色。 */
    private boolean startColorPending;

    /** 本回合已摸到的牌（-1 = 本回合尚未摸牌）。 */
    private int drawnCard = -1;
    /** 最近一次出牌座位（UI 高亮用）。 */
    private int lastPlaySeat = -1;
    /** 是否因牌堆耗尽而被迫结束（无人出完）。 */
    private boolean exhausted;

    /**
     * @param players 座位数 2..4
     * @param random  随机源（服务端注入，便于复现）
     */
    public UnoGame(int players, Random random) {
        if (players < UnoDeck.MIN_PLAYERS || players > UnoDeck.MAX_PLAYERS) {
            throw new IllegalArgumentException("座位数必须为 2..4，实际 " + players);
        }
        this.players = players;
        this.random = random == null ? new Random() : random;
        this.dealerDraw = new int[players];
        for (int s = 0; s < players; s++) {
            hands.add(new ArrayList<>());
            dealerDraw[s] = -1;
        }
    }

    // ==================================================================
    // 基本读取
    // ==================================================================

    public int players() {
        return players;
    }

    public int phase() {
        return phase;
    }

    public int currentSeat() {
        return currentSeat;
    }

    /** +1 = 顺时针，-1 = 逆时针。 */
    public int direction() {
        return direction;
    }

    public int activeColor() {
        return activeColor;
    }

    public int dealerSeat() {
        return dealerSeat;
    }

    public int winnerSeat() {
        return winnerSeat;
    }

    public int lastPlaySeat() {
        return lastPlaySeat;
    }

    public boolean exhausted() {
        return exhausted;
    }

    public int dealerDrawRound() {
        return dealerDrawRound;
    }

    /** 定庄阶段该座位抽到的牌（-1 = 未抽）。 */
    public int dealerDraw(int seat) {
        return dealerDraw[seat];
    }

    /** 只读手牌视图。 */
    public List<Integer> hand(int seat) {
        return Collections.unmodifiableList(hands.get(seat));
    }

    public int handSize(int seat) {
        return hands.get(seat).size();
    }

    public int drawPileSize() {
        return drawPile.size();
    }

    public int discardSize() {
        return discard.size();
    }

    /** 弃牌堆顶牌（当前有效牌），无则 -1。 */
    public int topCard() {
        return discard.isEmpty() ? -1 : discard.get(discard.size() - 1);
    }

    /** 本回合已摸到的牌（-1 = 未摸）。 */
    public int drawnCard() {
        return drawnCard;
    }

    public boolean hasDrawn() {
        return drawnCard >= 0;
    }

    /** 起始牌为 Wild 时，是否等待先手选色。 */
    public boolean isStartColorPending() {
        return startColorPending;
    }

    private int nextSeat() {
        return Math.floorMod(currentSeat + direction, players);
    }

    private void advance(int steps) {
        currentSeat = Math.floorMod(currentSeat + direction * steps, players);
    }

    private void beginTurn() {
        drawnCard = -1;
    }

    // ==================================================================
    // 定庄
    // ==================================================================

    /**
     * 定庄阶段：让 {@code seat} 抽一张比大小的牌。
     *
     * @return {@link #DRAW_OK} / {@link #DRAW_TIE_REDRAW} / {@link #DRAW_DEALER_DECIDED}；出错返回 -1
     */
    public int drawForDealer(int seat) {
        if (phase != PHASE_DEALER_DRAW || seat < 0 || seat >= players || dealerDraw[seat] >= 0) {
            return -1;
        }
        if (drawPile.isEmpty()) {
            drawPile.addAll(shuffled(UnoDeck.freshDeck()));
        }
        dealerDraw[seat] = drawPile.remove(drawPile.size() - 1);

        for (int s = 0; s < players; s++) {
            if (dealerDraw[s] < 0) {
                return DRAW_OK;
            }
        }
        return evaluateDealerDraw();
    }

    /**
     * 定庄阶段：**所有还没抽的座位一次性各抽一张**（需求：四家同时抽、同时提示）。
     * <p>
     * 与 {@link #drawForDealer(int)} 的区别只在"什么时候抽"：这里一次把本轮所有人的牌都发下来，
     * 牌桌层随后把四张牌同时亮在该座位自己的出牌区，展示 2 秒再结算。
     *
     * @return {@link #DRAW_TIE_REDRAW} / {@link #DRAW_DEALER_DECIDED}；没有可抽的座位或阶段不符返回 -1
     */
    public int drawAllForDealer() {
        if (phase != PHASE_DEALER_DRAW) {
            return -1;
        }
        boolean any = false;
        for (int s = 0; s < players; s++) {
            if (dealerDraw[s] >= 0) {
                continue;
            }
            if (drawPile.isEmpty()) {
                drawPile.addAll(shuffled(UnoDeck.freshDeck()));
            }
            dealerDraw[s] = drawPile.remove(drawPile.size() - 1);
            any = true;
        }
        return any ? evaluateDealerDraw() : -1;
    }

    /**
     * 比大小：数字牌按数字，其余算 0；并列最大 → 全部重抽。
     */
    private int evaluateDealerDraw() {
        int best = -1;
        for (int s = 0; s < players; s++) {
            best = Math.max(best, dealerPower(dealerDraw[s]));
        }
        int winners = 0;
        for (int s = 0; s < players; s++) {
            if (dealerPower(dealerDraw[s]) == best) {
                winners++;
            }
        }
        if (winners > 1) {
            // 抽的牌不用还，整副重新洗牌即可（等价于官方「放回牌堆重新洗牌」）
            for (int s = 0; s < players; s++) {
                dealerDraw[s] = -1;
            }
            drawPile.clear();
            dealerDrawRound++;
            return DRAW_TIE_REDRAW;
        }
        for (int s = 0; s < players; s++) {
            if (dealerPower(dealerDraw[s]) == best) {
                dealerSeat = s;
                break;
            }
        }
        return DRAW_DEALER_DECIDED;
    }

    /** 定庄比大小用的数值：数字牌 = 面值，功能牌 / 野牌 = 0。 */
    public static int dealerPower(int cardId) {
        return UnoDeck.kind(cardId) == UnoDeck.KIND_NUMBER ? UnoDeck.number(cardId) : 0;
    }

    // ==================================================================
    // 发牌
    // ==================================================================

    /**
     * 定庄完成后洗牌发牌：每人 7 张，翻一张起始牌，先手 = 庄家左手边。
     *
     * @return null 表示成功，否则为错误文本
     */
    public String deal() {
        if (phase != PHASE_DEALER_DRAW) {
            return "当前阶段无法发牌。";
        }
        if (dealerSeat < 0) {
            return "还没定出庄家。";
        }
        for (List<Integer> hand : hands) {
            hand.clear();
        }
        discard.clear();
        // 定庄比大小的牌到这里就作废了：它们已经从牌堆里拿出来过、之后又会随洗牌回到牌堆，
        // 完全可能“跑到某个玩家手上”。需求就是「抽完庄家之后这些牌立刻消失」，
        // 所以这里把记录一并清掉，客户端再也没有可显示它们的来源（见 UnoTable#sync）。
        for (int s = 0; s < players; s++) {
            dealerDraw[s] = -1;
        }
        drawnCard = -1;
        lastPlaySeat = -1;
        winnerSeat = -1;
        startColorPending = false;
        exhausted = false;
        direction = 1;

        drawPile.clear();
        drawPile.addAll(shuffled(UnoDeck.freshDeck()));
        for (int round = 0; round < UnoDeck.HAND_SIZE; round++) {
            for (int s = 0; s < players; s++) {
                hands.get(s).add(drawPile.remove(drawPile.size() - 1));
            }
        }
        for (List<Integer> hand : hands) {
            UnoDeck.sortHand(hand);
        }

        // 先手 = 庄家左手边（顺时针下一位）
        currentSeat = Math.floorMod(dealerSeat + 1, players);
        phase = PHASE_PLAYING;

        String err = flipStartCard();
        if (err != null) {
            return err;
        }
        beginTurn();
        return null;
    }

    /**
     * 翻起始牌并按官方规则处理特效：
     * <ul>
     *   <li>Wild+4 → 放回牌堆重洗，重新翻；</li>
     *   <li>Wild → 先手需先选色（{@link #isStartColorPending()}）；</li>
     *   <li>跳过 → 先手被跳过；</li>
     *   <li>反转 → 方向取反，改由庄家先出；</li>
     *   <li>+2 → 先手摸 2 张并被跳过。</li>
     * </ul>
     */
    private String flipStartCard() {
        for (int guard = 0; guard < 64; guard++) {
            if (drawPile.isEmpty()) {
                return "牌堆异常：无法翻起始牌。";
            }
            int card = drawPile.remove(drawPile.size() - 1);
            int kind = UnoDeck.kind(card);
            if (kind == UnoDeck.KIND_WILD_DRAW_FOUR) {
                // 官方：起始牌是 Wild+4 时放回牌堆重新洗牌再翻
                drawPile.add(card);
                List<Integer> reshuffled = shuffled(new ArrayList<>(drawPile));
                drawPile.clear();
                drawPile.addAll(reshuffled);
                continue;
            }
            discard.add(card);
            if (UnoDeck.isWild(card)) {
                activeColor = -1;
                startColorPending = true;
                return null;
            }
            activeColor = UnoDeck.color(card);
            // 注意：起始牌的特效是**施加在先手身上**（不是先手打出的），所以这里只推进 1 步
            switch (kind) {
                case UnoDeck.KIND_SKIP -> advance(1);
                case UnoDeck.KIND_REVERSE -> {
                    if (players == 2) {
                        // 2 人局反转等同跳过 → 先手被跳过，改由庄家先出
                        advance(1);
                    } else {
                        direction = -direction;
                        currentSeat = dealerSeat;
                    }
                }
                case UnoDeck.KIND_DRAW_TWO -> {
                    forceDraw(currentSeat, 2);
                    advance(1);
                }
                default -> {
                    // 数字牌，正常开始
                }
            }
            return null;
        }
        return "牌堆异常：起始牌重洗次数过多。";
    }

    /**
     * 起始牌为 Wild 时，由先手选色。
     *
     * @return null 表示成功
     */
    public String chooseStartColor(int seat, int color) {
        if (phase != PHASE_PLAYING || !startColorPending) {
            return "当前不需要选色。";
        }
        if (seat != currentSeat) {
            return "还没轮到你选色。";
        }
        if (color < 0 || color >= UnoDeck.COLOR_COUNT) {
            return "颜色不合法。";
        }
        activeColor = color;
        startColorPending = false;
        return null;
    }

    // ==================================================================
    // 出牌 / 摸牌
    // ==================================================================

    /** 该座位当前能打出的牌（升序）。 */
    public List<Integer> playableCards(int seat) {
        List<Integer> out = new ArrayList<>();
        if (phase != PHASE_PLAYING || seat != currentSeat || startColorPending) {
            return out;
        }
        List<Integer> hand = hands.get(seat);
        if (hasDrawn()) {
            // 摸牌后只能打刚摸到的那张
            if (hand.contains(drawnCard) && isLegal(drawnCard, hand)) {
                out.add(drawnCard);
            }
            return out;
        }
        for (int id : hand) {
            if (isLegal(id, hand)) {
                out.add(id);
            }
        }
        return out;
    }

    /** 牌是否合法（含 Wild+4 的「手里没有当前颜色才能打」限制）。 */
    public boolean isLegal(int cardId, List<Integer> hand) {
        if (activeColor < 0) {
            return true;
        }
        if (UnoDeck.isWild(cardId)) {
            if (UnoDeck.kind(cardId) == UnoDeck.KIND_WILD_DRAW_FOUR) {
                for (int id : hand) {
                    if (UnoDeck.color(id) == activeColor) {
                        return false;
                    }
                }
            }
            return true;
        }
        if (UnoDeck.color(cardId) == activeColor) {
            return true;
        }
        int top = topCard();
        if (top < 0) {
            return true;
        }
        if (UnoDeck.kind(top) == UnoDeck.KIND_NUMBER
                && UnoDeck.kind(cardId) == UnoDeck.KIND_NUMBER) {
            return UnoDeck.number(cardId) == UnoDeck.number(top);
        }
        return UnoDeck.kind(cardId) == UnoDeck.kind(top) && UnoDeck.kind(cardId) != UnoDeck.KIND_NUMBER;
    }

    /**
     * 出牌前的<b>通用校验</b>（不含野牌的颜色参数）：回合 / 摸牌限制 / 是否在手上 / 是否合法。
     * <p>
     * UI 必须在「进入野牌选色态之前」先过这一关：选色态的按钮组只有四个颜色，
     * 没有「取消 / 抽牌 / 跳过」，一旦进去又出不了牌，玩家就被锁死在选色态。
     *
     * @return null 表示可以出，否则为不能出的原因
     */
    public String checkPlay(int seat, int cardId) {
        String err = checkTurn(seat);
        if (err != null) {
            return err;
        }
        if (hasDrawn() && cardId != drawnCard) {
            return "摸牌后只能打出刚摸到的牌。";
        }
        List<Integer> hand = hands.get(seat);
        if (!hand.contains(cardId)) {
            return "这张牌不在你手上。";
        }
        if (!isLegal(cardId, hand)) {
            if (UnoDeck.kind(cardId) == UnoDeck.KIND_WILD_DRAW_FOUR) {
                // isLegal 对 Wild+4 只有这一条限制：手里还有当前颜色的牌
                return "手里还有当前颜色的牌，现在不能打「+4 王牌」。";
            }
            return "这张牌出不了（需要同色或同数字/同功能）。";
        }
        return null;
    }

    /**
     * 正常出牌。
     *
     * @param chosenColor 仅野牌需要（0..3），其余传 -1
     * @return null 表示成功，否则为错误文本
     */
    public String play(int seat, int cardId, int chosenColor) {
        String err = checkPlay(seat, cardId);
        if (err != null) {
            return err;
        }
        if (UnoDeck.isWild(cardId) && (chosenColor < 0 || chosenColor >= UnoDeck.COLOR_COUNT)) {
            return "野牌需要先选一个颜色。";
        }
        return doPlay(seat, cardId, chosenColor);
    }

    /** 摸牌后打出刚摸到的那张。 */
    public String playDrawn(int seat, int chosenColor) {
        if (!hasDrawn()) {
            return "你这一回合还没摸牌。";
        }
        return play(seat, drawnCard, chosenColor);
    }

    private String doPlay(int seat, int cardId, int chosenColor) {
        List<Integer> hand = hands.get(seat);
        hand.remove(Integer.valueOf(cardId));
        discard.add(cardId);
        lastPlaySeat = seat;
        activeColor = UnoDeck.isWild(cardId) ? chosenColor : UnoDeck.color(cardId);

        int kind = UnoDeck.kind(cardId);
        if (kind == UnoDeck.KIND_SKIP) {
            advance(2);
        } else if (kind == UnoDeck.KIND_REVERSE) {
            if (players == 2) {
                // 官方：2 人局反转等同跳过 → 对手被跳过，自己继续出（方向不翻转）
                advance(2);
            } else {
                direction = -direction;
                advance(1);
            }
        } else if (kind == UnoDeck.KIND_DRAW_TWO || kind == UnoDeck.KIND_WILD_DRAW_FOUR) {
            int victim = nextSeat();
            forceDraw(victim, UnoDeck.drawAmount(cardId));
            advance(2);
        } else {
            advance(1);
        }

        if (hand.isEmpty()) {
            phase = PHASE_FINISHED;
            winnerSeat = seat;
        } else {
            beginTurn();
        }
        return null;
    }

    /**
     * 摸牌（可自愿摸；摸到后本回合只能出它或跳过）。
     *
     * @return null 表示成功
     */
    public String draw(int seat) {
        String err = checkTurn(seat);
        if (err != null) {
            return err;
        }
        if (hasDrawn()) {
            return "这一回合已经摸过牌了。";
        }
        int card = drawOne();
        if (card < 0) {
            // 牌堆彻底耗尽（弃牌堆只剩一张）：直接结束本局
            finishExhausted();
            return null;
        }
        hands.get(seat).add(card);
        UnoDeck.sortHand(hands.get(seat));
        drawnCard = card;
        return null;
    }

    /**
     * 摸牌后跳过（无论摸到的牌能不能出都可以跳过）。
     *
     * @return null 表示成功
     */
    public String pass(int seat) {
        String err = checkTurn(seat);
        if (err != null) {
            return err;
        }
        if (!hasDrawn()) {
            return "必须先摸牌才能跳过。";
        }
        advance(1);
        beginTurn();
        return null;
    }

    private String checkTurn(int seat) {
        if (phase != PHASE_PLAYING) {
            return "本局已结束。";
        }
        if (startColorPending) {
            return "起始牌是野牌，请先选一个颜色。";
        }
        if (seat != currentSeat) {
            return "还没轮到你。";
        }
        return null;
    }

    // ==================================================================
    // 摸牌堆 / 弃牌堆
    // ==================================================================

    /** 从摸牌堆取一张；不足时把弃牌堆（留顶牌）洗回；彻底没了返回 -1。 */
    private int drawOne() {
        if (drawPile.isEmpty()) {
            reshuffleDiscard();
        }
        if (drawPile.isEmpty()) {
            return -1;
        }
        return drawPile.remove(drawPile.size() - 1);
    }

    /** 给某座位强制摸 {@code amount} 张（+2 / +4 结算）。 */
    private void forceDraw(int seat, int amount) {
        for (int i = 0; i < amount; i++) {
            int card = drawOne();
            if (card < 0) {
                finishExhausted();
                return;
            }
            hands.get(seat).add(card);
        }
        UnoDeck.sortHand(hands.get(seat));
    }

    /** 弃牌堆洗回摸牌堆：保留最顶一张作为当前有效牌。 */
    private void reshuffleDiscard() {
        if (discard.size() <= 1) {
            return;
        }
        int top = discard.remove(discard.size() - 1);
        List<Integer> recycled = new ArrayList<>(discard);
        discard.clear();
        discard.add(top);
        drawPile.addAll(shuffled(recycled));
    }

    private void finishExhausted() {
        exhausted = true;
        phase = PHASE_FINISHED;
        winnerSeat = -1;
    }

    private List<Integer> shuffled(List<Integer> list) {
        Collections.shuffle(list, random);
        return list;
    }

    // ==================================================================
    // 结算
    // ==================================================================

    /** 每个座位剩余手牌的官方总分；赢家（或无人出完时全体）照算。 */
    public int[] handPoints() {
        int[] out = new int[players];
        for (int s = 0; s < players; s++) {
            out[s] = handPoints(s);
        }
        return out;
    }

    public int handPoints(int seat) {
        int sum = 0;
        for (int id : hands.get(seat)) {
            sum += UnoDeck.points(id);
        }
        return sum;
    }

    /**
     * 赢家收益：Σ（其余每人剩余手牌分 × k）。
     *
     * @param k 系数（由第一个入座的玩家设定）
     * @return 赢家应得的币数；本局无人出完（{@link #exhausted()}）返回 0
     */
    public double winnerGain(double k, int winner) {
        if (winner < 0) {
            return 0;
        }
        double gain = 0;
        for (int s = 0; s < players; s++) {
            if (s != winner) {
                gain += handPoints(s) * k;
            }
        }
        return gain;
    }

    /** 聊天面板用的名次摘要。 */
    public String summary() {
        StringBuilder sb = new StringBuilder();
        if (winnerSeat >= 0) {
            sb.append("§a座位 ").append(winnerSeat + 1).append(" 出完牌，本局结束。");
        } else if (exhausted) {
            sb.append("§e牌堆耗尽，本局无人出完。");
        }
        int[] pts = handPoints();
        for (int s = 0; s < players; s++) {
            sb.append('\n').append("§7座位 ").append(s + 1).append("：剩 ")
                    .append(hands.get(s).size()).append(" 张 / ").append(pts[s]).append(" 分");
        }
        return sb.toString();
    }
}
