package com.tabletopgame.item;

import cn.nukkit.item.customitem.CustomItemDefinition;
import cn.nukkit.item.customitem.ItemCustom;
import cn.nukkit.network.protocol.types.inventory.creative.CreativeItemCategory;

/**
 * 「定位器」（{@code tabletopgame:locator}）：UNO 牌桌的持握道具，思路完全来自斗地主的激光笔
 * （{@code Doudizhu/src/main/java/top/doudizhu/item/CursorItem.java}）。
 *
 * <h3>为什么需要它</h3>
 * 手牌是<b>悬空</b>在台面上方的（第一行底边离台面 0.26 格，第二行起更高），
 * 而基岩客户端的准星只认「方块」和「实体」—— 两样都没碰着时，客户端<b>不一定</b>会把
 * 右键交互发给服务端，于是「瞄着牌点没反应」。而**手持物品**右键时，客户端一定会发
 * 「使用物品」事务（MOT 的 {@code UseItemProcessor_v113} 收到后固定派发
 * {@code PlayerInteractEvent(RIGHT_CLICK_AIR)}），服务端就一定能拿到这次信号，
 * 再用自己的射线判定去决定点到了哪张牌 / 哪个按钮。
 *
 * <h3>行为约定</h3>
 * <ul>
 *   <li>本身**没有任何用途**（不是食物也不是工具）—— 右键不会在世界里留下任何东西；</li>
 *   <li>手持它右键牌桌：与空手一样（命中手牌/按钮就操作，没命中就开菜单）；</li>
 *   <li>手持它且准星落在牌上时，沿视线在命中点放一颗**白色光点**
 *       （{@code tabletopgame:locator_dot}，2026-10-15 起为白色）；</li>
 *   <li>开局由牌桌自动发放、离桌自动回收（见 {@code UnoTable.startRound()} /
 *       {@code UnoManager.ensureLocator/takeLocator}）。</li>
 * </ul>
 *
 * 资源侧（由 {@code tools/uno/build_locator.py} 生成）：模型
 * {@code models/entity/uno/locator.geo.json} + 手持附加物 {@code attachables/uno/locator.json}
 * + 贴图 {@code textures/tabletopgame/uno/locator.png} + 图标键 {@link #ICON}。
 */
public class LocatorItem extends ItemCustom {

    public static final String IDENTIFIER = "tabletopgame:locator";

    /** 背包图标在 {@code textures/item_texture.json} 里的键名。 */
    public static final String ICON = "tabletopgame_locator";

    public LocatorItem() {
        super(IDENTIFIER, "定位器", ICON);
    }

    @Override
    public CustomItemDefinition getDefinition() {
        return CustomItemDefinition
                .simpleBuilder(this, CreativeItemCategory.ITEMS)
                .build();
    }

    /** 每人只需一把，不叠加。 */
    @Override
    public int getMaxStackSize() {
        return 1;
    }
}
