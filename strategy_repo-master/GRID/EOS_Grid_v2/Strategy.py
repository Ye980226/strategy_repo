from vnpy.trader.utils.templates.orderTemplate import *
import talib as ta


########################################################################
class StrategyEOSGridV2(OrderTemplate):
    className = 'StrategyEOSGridV2'
    author = 'Rich'

    # 参数列表，保存了参数的名称
    paramList = [
        'className',
        'author',
        'symbolList',
        'maxBarSize',  # 预加载的bar数
        'barPeriod',  # 根据n根小时线计算阻力支撑位和主力支撑线中枢以及ATR（当前环境的波动性）
        'continuousCalmHours',  # 连续多少小时均线粘合 视为当前行情稳定，计算这么多小时均线价格均值作为网格设置的中枢
        'calmMAGap',  # 长短均线的gap在这个百分比范围内，才算行情稳定。
        'longMALen',  # 长均线bar数
        'shortMALen',  # 短均线bar数
        'trendEMALen',  # 用于判断趋势的均线bar数
        'slopeLen',  # 用于判断趋势斜率的bar数
        'maxSlope',  # 允许开仓的趋势斜率最大值
        'longMAMidMaxGap',  # 长均线价格偏离阻力支撑线中枢超过x，则不再发单，重新计算条件是否满足
        'highLowLimitMaxGap',  # 网格的上下边界最高不超过x，超过则不再发单
        'ATRMaxValue',  # ATR值超过该阈值不进场
        'gridGap',  # 网格的gap
        'gridLevel',  # 一共铺n*2个level的网（向上n个level，向下n个level）
        'gridLevelMaxPos',  # 每个Level最多允许多大的仓位
        'takeProfit',  # 网格单的止盈百分比
        'rencentHighLowBars',  # 用n根bar判断近期高低点，突破该区间的话提前止损
        'lot',  # 基础下单手数
        'orderWaitingTime',  # 进场挂单最大等待时间（按秒,未成交则撤单）
        "timeframeMap",  # 不同策略任务的时间周期
    ]

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
        self.symbol = self.symbolList[0]  # 待交易的品种
        self.lastBarTimeDict = {}  # 用于记录K线的最新时间
        self.orderDict = {
            "buy": set(),
            "short": set(),
            "gridLevel": {}
        }
        for i in range(1, self.gridLevel + 1):  # 初始化每个level的仓位和订单号
            self.orderDict["gridLevel"][i] = set()
            self.orderDict["gridLevel"][-i] = set()

        # 和网格设置相关的全局变量
        self.highlimit = 0  # 上穿该阈值，则认为已经突破了当前的最高阻力位，撤网
        self.lowlimit = 0  # 下穿该阈值，则认为已经下破了当前的最低阻力位，撤网
        self.recentHighLow = {"high": 0, "low": 0}  # 用于记录最近较长一段时间的高低价，用于判断趋势突破,提前撤网出场
        self.grid0 = 0  # 挂单价格中枢 用continuousCalmHours个小时长均线的均值去设置
        self.canOpen = False  # 是否可以挂网格单的开关

    # 准备不同周期的K线数据
    def prepare_data(self):
        for timeframe in list(set(self.timeframeMap.values())):
            self.registerOnBar(self.symbol, timeframe, None)
            self.lastBarTimeDict[timeframe] = None

    # 判断是否产生了个新bar——有新bar则进行信号计算
    def barPrepared(self, period):
        am = self.getArrayManager(self.symbol, period)
        if not am.inited:
            self.writeCtaLog("am is not inited:%s" % (period,))
            return False, None
        if self.lastBarTimeDict[period] is None or am.datetime[-1] > self.lastBarTimeDict[period]:
            return True, am
        else:
            return False, None

    # 更新记录am中最新一根K线的时间
    def updateLastBarTime(self):
        for timeframe in list(set(self.timeframeMap.values())):
            self.lastBarTimeDict[timeframe] = self.getArrayManager(self.symbol, timeframe).datetime[-1]

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.setArrayManagerSize(self.maxBarSize)  # 定义预加载bar数
        self.prepare_data()  # 准备不同周期的K线数据

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略"""
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略"""
        self.putEvent()

    # -----------------------------------------------------------------------
    def outputPosAndOrd(self):
        buy = 0
        short = 0
        gridLevel = []
        for i in range(1, self.gridLevel + 1):
            gridLevel.append({i: self.getLevelPos(i), -i: self.getLevelPos(-i)})
            buy += gridLevel[-1][-i]
            short += gridLevel[-1][i]
        self.writeCtaLog('打印网格当前的订单和仓位')
        self.writeCtaLog('网格订单:%s' % (self.orderDict["gridLevel"],))
        self.writeCtaLog('网格仓位:%s' % (gridLevel,))
        self.writeCtaLog('各仓位汇总:')
        self.writeCtaLog("buy:%s, short:%s"%(buy, short))

    # ----------------------------------------------------------------------
    # 策略主体
    # ----------------------------------------------------------------------
    # 实盘在5sBar中洗价
    def on5sBar(self, bar):
        self.checkOnPeriodStart(bar)
        self.checkOnPeriodEnd(bar)

    # 定时清除已经出场的单
    def delOrderID(self, opIDsets):
        for vtOrderID in list(opIDsets):
            op = self._orderPacks[vtOrderID]
            # 检查是否完全平仓
            if self.orderClosed(op):
                # 在记录中删除
                opIDsets.discard(vtOrderID)

    # 定时运行该方法，将已经结束的单从存放的集合中清除
    def delGridOrderID(self):
        self.delOrderID(self.orderDict["buy"])
        self.delOrderID(self.orderDict["short"])
        for i in range(1, self.gridLevel + 1):
            self.delOrderID(self.orderDict["gridLevel"][i])
            self.delOrderID(self.orderDict["gridLevel"][-i])

    def onBar(self, bar):
        # 必须继承父类方法
        super().onBar(bar)

        # on bar下触发回测洗价逻辑
        engineType = self.getEngineType()  # 判断engine模式
        if engineType == 'backtesting':
            # 定时控制，开始
            self.checkOnPeriodStart(bar)
            # 回测时的下单手数按此方法调整
            self.lot = round(100 / bar.close, 4)
            self.gridLevelMaxPos = self.lot * 10

        # 定时从集合中清除已出场的单
        self.delGridOrderID()

        # 执行策略逻辑
        self.strategy(bar.close, bar.high, bar.low,
                      pivotPeriod=self.timeframeMap["pivotPeriod"],
                      highLowLimitPeriod=self.timeframeMap["highLowLimitPeriod"],
                      moveStopLossPeriod=self.timeframeMap["moveStopLossPeriod"],
                      envPeriod=self.timeframeMap["envPeriod"],
                      )
        # 定时控制--结束
        self.checkOnPeriodEnd(bar)
        # 日志打印网格当前的订单和仓位
        self.outputPosAndOrd()

    # ----------------------------------------------------------------------
    # 策略主体
    # ----------------------------------------------------------------------
    def strategy(self,
                 marketPrice, high, low,
                 pivotPeriod="2h",
                 highLowLimitPeriod="1h",
                 moveStopLossPeriod="1h",
                 envPeriod="1h"
                 ):
        # 根据出场信号出场
        self.calRecentHighLow(pivotPeriod)  # 计算近期高低点，根据高低点判断是否出场
        exitSig = self.exitSignal(high, low)
        self.exitOrder(exitSig)

        # 计算最新上下边界
        self.calHighLowLimit(highLowLimitPeriod)
        # 修改止损价格
        self.moveStopLoss(moveStopLossPeriod)

        # 计算环境
        self.calEnv(envPeriod)
        # 根据环境看是否下单（挂网）
        if self.canOpen:
            entrySig = self.entrySignal(marketPrice)
            if entrySig != 0:  # 有下单信号
                self.entryOrder(entrySig, marketPrice)

        # 更新记录am中最新一根K线的时间
        self.updateLastBarTime()

    # 计算最新上下边界
    def calHighLowLimit(self, period="1h"):
        barPrepared, am = self.barPrepared(period)
        if barPrepared:
            highlimit = am.high[-self.barPeriod:].max()
            lowlimit = am.low[-self.barPeriod:].min()
            mid = (highlimit + lowlimit) / 2
            if highlimit / lowlimit - 1 <= self.highLowLimitMaxGap:
                self.highlimit = mid * (1 + self.highLowLimitMaxGap / 2)
                self.lowlimit = mid * (1 - self.highLowLimitMaxGap / 2)
                self.writeCtaLog("update-highlimit:%s,lowlimit:%s" % (self.highlimit, self.lowlimit))

    # 按某一时间间隔修改止损价格-默认1h
    def moveStopLoss(self, period="1h"):
        if self.highlimit != 0 and self.lowlimit != 0:
            barPrepared, am = self.barPrepared(period)
            if barPrepared:
                for orderID in list(self.orderDict["short"]):
                    op = self._orderPacks[orderID]
                    if self.isAutoExit(op):
                        op.info["_AutoExitInfo"].stoploss = self.highlimit
                for orderID in list(self.orderDict["buy"]):
                    op = self._orderPacks[orderID]
                    if self.isAutoExit(op):
                        op.info["_AutoExitInfo"].stoploss = self.lowlimit

    # 计算近期高低点
    def calRecentHighLow(self, period="2h"):
        barPrepared, am = self.barPrepared(period)
        if barPrepared:
            self.recentHighLow["high"] = am.high[-self.rencentHighLowBars:].max()
            self.recentHighLow["low"] = am.low[-self.rencentHighLowBars:].min()
            self.writeCtaLog(
                "update-recentHighLow.high:%s,low:%s" % (self.recentHighLow["high"], self.recentHighLow["low"]))

    # 平仓信号
    def exitSignal(self, high, low):
        sig = 0
        if self.recentHighLow["high"] != 0 and self.recentHighLow["low"] != 0:
            if high > self.recentHighLow["high"]:
                sig = 1
            if low < self.recentHighLow["low"]:
                sig = -1
        return sig

    # 下单出场
    def exitOrder(self, sig):
        if sig < 0:  # 全平多头
            for vtOrderID in list(self.orderDict["buy"]):
                op = self._orderPacks[vtOrderID]
                self.composoryClose(op)
        if sig > 0:  # 全平空头
            for vtOrderID in list(self.orderDict["short"]):
                op = self._orderPacks[vtOrderID]
                self.composoryClose(op)

    # 计算环境
    def calEnv(self, period="1h"):
        barPrepared, am = self.barPrepared(period)
        if barPrepared:
            # 环境条件1:不允许允许的最大波动范围
            if am.high[-self.barPeriod:].max() / am.low[
                                                 -self.barPeriod:].min() - 1 > self.highLowLimitMaxGap:  # 超过允许的最大波动范围
                self.writeCtaLog("highlimit / lowlimit - 1 > self.highLowLimitMaxGap")
                self.canOpen = False
                return
            # 环境条件2:ATR衡量波动率：只有当中期波动率在某个阈值之下，并且处于下降状态时，才允许开仓
            ATRSeries = ta.ATR(am.high, am.low, am.close, self.barPeriod) / am.close[-1]
            ATR = ATRSeries[-1]
            ATRMA = ta.MA(ATRSeries, self.barPeriod)
            if ATRMA[-1] > ATRMA[-2] or ATR > ATRMA[-1] or ATR > self.ATRMaxValue:  # ATR在增大 或当前ATR高过阈值
                self.writeCtaLog("ATR is unsatisfied")
                self.canOpen = False
                return
            # 环境条件3: 每小时更新均线情况,用均线粘合度判断行情是否适合开仓
            shortMA = ta.MA(am.close, self.shortMALen)
            longMA = ta.MA(am.close, self.longMALen)
            mid = (am.high[-self.barPeriod:].max() + am.low[-self.barPeriod:].min()) / 2
            if max(longMA[-1], mid) / min(longMA[-1], mid) - 1 > self.longMAMidMaxGap:
                self.writeCtaLog("long MA vs mid is unsatisfied")
                self.canOpen = False
                return
            for i in range(1, self.continuousCalmHours + 1):
                big = max(shortMA[-i], longMA[-i])
                small = min(shortMA[-i], longMA[-i])
                if big / small - 1 > self.calmMAGap:
                    self.writeCtaLog("big / small - 1 > self.calmMAGap")
                    self.canOpen = False
                    return
            # 环境条件4:判断当前是否处于一个大的趋势行情中（长期EMA均线斜率较大）
            EMA = ta.EMA(am.close, self.trendEMALen)[-self.trendEMALen:]
            K = ta.LINEARREG_SLOPE(EMA, self.slopeLen)[-1] / am.close[-1]
            if abs(K) > self.maxSlope:
                self.writeCtaLog("abs(K) > self.maxSlope")
                self.canOpen = False
                return

            # 允许开仓,更新挂单中枢价格
            self.canOpen = True
            self.grid0 = longMA[-self.continuousCalmHours:].mean()
            self.writeCtaLog("CanOpen,update grid0=%s" % (self.grid0,))

    # 开仓信号
    def entrySignal(self, priceNow):
        sig = 0
        if self.grid0 * pow((1 + self.gridGap), self.gridLevel + 1) > priceNow > self.grid0:  # 处于开空阈值，且环境合适，考虑开空单
            sig = -1
        elif self.grid0 * pow((1 - self.gridGap), self.gridLevel + 1) < priceNow < self.grid0:  # 处于开多阈值，且环境合适，考虑开多单
            sig = 1
        return sig

    # 计算网格对应level上开了多少仓
    def getLevelPos(self, level):
        pos = 0
        for orderID in list(self.orderDict["gridLevel"][level]):
            op = self._orderPacks[orderID]
            openVolume = op.order.tradedVolume if op.order.status in constant.STATUS_FINISHED else op.order.totalVolume
            closedVolume = self.orderClosedVolume(op)
            pos += (openVolume - closedVolume)
        return pos

    # 根据当前价格所处的位置挂网进场
    def entryOrder(self, sig, priceNow):
        if sig < 0:
            for i in range(self.gridLevel, 0, -1):  # 倒序枚举网格level, 由远到近判断当前的价格位于网格的哪个level
                priceLevel = self.grid0 * pow((1 + self.gridGap), i)
                if priceNow >= priceLevel and self.getLevelPos(
                        i) + self.lot <= self.gridLevelMaxPos:  # 当前价格达到level进场条件且没达到该level最大开仓限制
                    tlo = self.timeLimitOrder(ctaBase.CTAORDER_SHORT, self.symbol, priceNow, self.lot,
                                              self.orderWaitingTime)
                    for orderID in tlo.vtOrderIDs:
                        # 将订单ID加到集合
                        self.orderDict["short"].add(orderID)
                        self.orderDict["gridLevel"][i].add(orderID)
                        op = self._orderPacks[orderID]
                        # 添加止损止盈
                        self.setAutoExit(op, self.highlimit, priceNow * (1 - self.takeProfit))
                        # 记录当前单对应哪个level的网
                        op.info["gridLevel"] = i
                    break
        elif sig > 0:
            for i in range(self.gridLevel, 0, -1):  # 倒序枚举网格level, 由远到近判断当前的价格位于网格的哪个level
                priceLevel = self.grid0 * pow((1 - self.gridGap), i)
                if priceNow <= priceLevel and self.getLevelPos(
                        -i) + self.lot <= self.gridLevelMaxPos:  # 当前价格达到level进场条件且没达到该level最大开仓限制
                    tlo = self.timeLimitOrder(ctaBase.CTAORDER_BUY, self.symbol, priceNow, self.lot,
                                              self.orderWaitingTime)
                    for orderID in tlo.vtOrderIDs:
                        # 将订单ID加到集合
                        self.orderDict["buy"].add(orderID)
                        self.orderDict["gridLevel"][-i].add(orderID)
                        op = self._orderPacks[orderID]
                        # 添加止损止盈
                        self.setAutoExit(op, self.lowlimit, priceNow * (1 + self.takeProfit))
                        # 记录当前单对应哪个level的网
                        op.info["gridLevel"] = -i
                    break
