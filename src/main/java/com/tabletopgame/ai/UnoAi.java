package com.tabletopgame.ai;

import com.tabletopgame.game.UnoDeck;

import java.util.List;
import java.util.Random;

/**
 * UNO 人机（三档）。
 * <p>
 * 决策只有两种：打某张牌（野牌附带颜色）或摸牌。摸牌之后由牌桌逻辑决定是否打出刚摸到的牌，
 * 本类用 {@link #shouldPlayDrawn} 给出建议。
 *
 * <ul>
 *   <li>{@link #LEVEL_EASY} 入门：在合法牌里随机挑。</li>
 *   <li>{@link #LEVEL_NORMAL} 进阶：优先同色数字牌，尽量把野牌留到最后；选色取手中最多的颜色。</li>
 *   <li>{@link #LEVEL_MASTER} 大师：在下家手牌很少时优先打 +2/+4/跳过/反转压制；
 *       否则保留功能牌；选色在「手中最多颜色」与「保留野牌」之间权衡。</li>
 * </ul>
 */
public final class UnoAi {

    public static final int LEVEL_EASY = 0;
    public static final int LEVEL_NORMAL = 1;
    public static final int LEVEL_MASTER = 2;

    /** 出牌建议。 */
    public record Decision(boolean draw, int cardId, int chosenColor) {

        public static Decision drawCard() {
            return new Decision(true, -1, -1);
        }

        public static Decision play(int cardId, int color) {
            return new Decision(false, cardId, color);
        }
    }

    private final int level;
    private final Random random;

    public UnoAi(int level, Random random) {
        this.level = Math.max(LEVEL_EASY, Math.min(LEVEL_MASTER, level));
        this.random = random == null ? new Random() : random;
    }

    public int level() {
        return level;
    }

    public static String levelName(int level) {
        return switch (level) {
            case LEVEL_EASY -> "入门";
            case LEVEL_MASTER -> "大师";
            default -> "进阶";
        };
    }

    /**
     * 回合决策。
     *
     * @param hand          自己的手牌
     * @param playable      {@link com.tabletopgame.game.UnoGame#playableCards(int)} 的结果
     * @param activeColor   当前有效颜色
     * @param nextHandSize  下家手牌张数（大师档用来判断是否值得压制；未知传 -1）
     */
    public Decision decide(List<Integer> hand, List<Integer> playable,
                           int activeColor, int nextHandSize) {
        if (playable.isEmpty()) {
            return Decision.drawCard();
        }
        if (level == LEVEL_EASY) {
            return play(playable.get(random.nextInt(playable.size())), hand, activeColor);
        }

        // 大师档：下家快出完了 → 优先压制
        if (level == LEVEL_MASTER && nextHandSize >= 0 && nextHandSize <= 2) {
            int best = -1;
            int bestWeight = -1;
            for (int id : playable) {
                int weight = attackWeight(id);
                if (weight > bestWeight) {
                    bestWeight = weight;
                    best = id;
                }
            }
            if (best >= 0 && bestWeight > 0) {
                return play(best, hand, activeColor);
            }
        }

        // 通用：野牌留到最后；同色数字优先；同色功能牌次之
        int chosen = -1;
        int bestScore = Integer.MIN_VALUE;
        for (int id : playable) {
            int score = keepScore(id, hand, activeColor);
            if (score > bestScore) {
                bestScore = score;
                chosen = id;
            }
        }
        return play(chosen, hand, activeColor);
    }

    /** 组装出牌建议：野牌自动带上选好的颜色。 */
    private Decision play(int cardId, List<Integer> hand, int activeColor) {
        return Decision.play(cardId, UnoDeck.isWild(cardId) ? chooseColor(hand) : -1);
    }

    /** 压制权重：+4 > +2 > 跳过 > 反转 > 其它。 */
    private static int attackWeight(int id) {
        return switch (UnoDeck.kind(id)) {
            case UnoDeck.KIND_WILD_DRAW_FOUR -> 5;
            case UnoDeck.KIND_DRAW_TWO -> 4;
            case UnoDeck.KIND_SKIP -> 3;
            case UnoDeck.KIND_REVERSE -> 2;
            default -> 0;
        };
    }

    /**
     * 出牌倾向分：越高越优先。
     * 原则 =「先用掉手上颜色多的牌」+「野牌尽量留着」+「数字牌优先于功能牌」。
     */
    private int keepScore(int id, List<Integer> hand, int activeColor) {
        int kind = UnoDeck.kind(id);
        if (kind == UnoDeck.KIND_WILD || kind == UnoDeck.KIND_WILD_DRAW_FOUR) {
            return -100 + (kind == UnoDeck.KIND_WILD_DRAW_FOUR ? 1 : 0);
        }
        int color = UnoDeck.color(id);
        int sameColor = 0;
        for (int c : hand) {
            if (UnoDeck.color(c) == color) {
                sameColor++;
            }
        }
        int score = sameColor * 4;
        if (color == activeColor) {
            score += 6;
        }
        score += switch (kind) {
            case UnoDeck.KIND_NUMBER -> 6 - Math.abs(UnoDeck.number(id) - 5) / 2;
            case UnoDeck.KIND_SKIP -> 2;
            case UnoDeck.KIND_REVERSE -> 1;
            default -> 2; // DRAW_TWO
        };
        return score;
    }

    /** 野牌选色：手里最多的颜色；全是野牌则随机。 */
    public int chooseColor(List<Integer> hand) {
        int[] counts = new int[UnoDeck.COLOR_COUNT];
        for (int id : hand) {
            if (!UnoDeck.isWild(id)) {
                counts[UnoDeck.color(id)]++;
            }
        }
        int best = 0;
        int bestCount = -1;
        boolean tie = false;
        for (int c = 0; c < UnoDeck.COLOR_COUNT; c++) {
            if (counts[c] > bestCount) {
                bestCount = counts[c];
                best = c;
                tie = false;
            } else if (counts[c] == bestCount) {
                tie = true;
            }
        }
        if (bestCount <= 0) {
            return random.nextInt(UnoDeck.COLOR_COUNT);
        }
        if (tie && level == LEVEL_EASY) {
            return random.nextInt(UnoDeck.COLOR_COUNT);
        }
        return best;
    }

    /**
     * 摸到牌之后要不要立刻打出。
     * <p>入门档有牌就打；进阶/大师档会把野牌留到后面（手牌还多时）。
     */
    public boolean shouldPlayDrawn(int drawnCard, List<Integer> hand, boolean legal) {
        if (!legal || drawnCard < 0) {
            return false;
        }
        if (level == LEVEL_EASY) {
            return true;
        }
        if (UnoDeck.isWild(drawnCard) && hand.size() > 3) {
            return false;
        }
        return true;
    }
}
