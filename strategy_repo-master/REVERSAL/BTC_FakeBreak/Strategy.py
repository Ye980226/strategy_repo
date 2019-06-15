from vnpy.trader.utils.templates.orderTemplate import *
from SIGNALBASE import ENVIRONMENT, OPENSIGNAL, CLOSESIGNAL

'''
一个震荡行情下做的反转策略:
用ADX判断当前行情是否处于震荡环境
用价量相关度分别制作指标判断是否迎来了多头或空头的反转
ATR过滤掉一些波动率过低的场景，避免频繁开仓损失手续费
'''


########################################################################
class StrategyBTCFakeBreak(OrderTemplate):
    className = 'StrategyBTCFakeBreak'
    author = 'Rich'

    # 参数列表，保存了参数的名称
    paramList = [
        'className',
        'author',
        'symbolList',
        'maxBarSize', # 预加载的bar数
        "corrLen", # 用n根bar计算价量相关性指标
        "posRange", # 计算近期收益变化的bar数的范围要求
        "negDirPctRange",# 与信号方向相反的近期收益范围要求（不能太大也不能太小，保持一定的波动性）
        "sameDirPctLimit",# 与信号方向相同的近期收益最大值（不能太大，否则追进去风险比较高）
        "minCorrLong2",# 多头开仓的阈值2
        "minCorrLong1",# 多头开仓的阈值1
        "minCorrShort1",# 空头开仓的阈值1
        "ATRLen",# 用n根bar计算ATR
        "ATRMALen",# 用ATR的n个值计算均值
        "minATRLimit",# 允许的ATR最小值
        "ADXLen",# ADX bar数
        "ADXThreshold",# ADX阈值 大于该阈值倾向于趋势行情,策略不开仓
        "exitCorrLong",# 多头信号出场阈值
        "exitCorrLongRange",# 多头信号出场范围（第二种出场阈值）
        "takeProfit", # 止盈百分比
        "stopLoss",# 止损百分比
        'lot', # 单次下单手数
        'holdWaitingTime',# 等待n秒未实现预期收益出场
        'expectedReturn',# 等待n秒未实现expectedReturn出场
        'orderWaitingTime',# 进场挂单最大等待时间（按秒,未成交则撤单）
        'timeframeMap',# 不同策略任务的时间周期
    ]

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
        self.orderDict = {"buy":set(), "short":set()} # 用于记录不同方向开仓订单的orderID
        self.symbol = self.symbolList[0]  # 待交易的品种
        self.lastBarTimeDict = {}  # 用于记录K线的最新时间

    # 准备不同周期的K线数据
    def prepare_data(self):
        for timeframe in list(set(self.timeframeMap.values())):
            self.registerOnBar(self.symbol, timeframe, None)
            self.lastBarTimeDict[timeframe] = None

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

    def getPos(self, key):
        pos = 0
        for orderID in list(self.orderDict[key]):
            op = self._orderPacks[orderID]
            openVolume = op.order.tradedVolume
            closedVolume = self.orderClosedVolume(op)
            pos += (openVolume - closedVolume)
        return pos

    def outputPos(self):
        self.writeCtaLog('打印当前的订单和仓位')
        self.writeCtaLog('订单:%s' % (self.orderDict,))
        self.writeCtaLog('仓位-buy:%s;short:%s' % (self.getPos("buy"),self.getPos("short")))

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
        # 定时清除已出场的单
        self.delOrderID(self.orderDict["buy"])
        self.delOrderID(self.orderDict["short"])

        # 执行策略逻辑
        self.strategy(bar.close,
                      trendPeriod=self.timeframeMap["trendPeriod"],
                      volPeriod=self.timeframeMap["volPeriod"],
                      entrySigPeriod=self.timeframeMap["entrySigPeriod"],
                      exitSigPeriod=self.timeframeMap["exitSigPeriod"],
                      )

        # 定时控制--结束
        self.checkOnPeriodEnd(bar)
        # 日志打印当前的订单和仓位
        self.outputPos()

    # ----------------------------------------------------------------------
    # 策略主体
    # ----------------------------------------------------------------------
    def strategy(self,
                 marketPrice,
                 trendPeriod="1h",
                 volPeriod="15m",
                 entrySigPeriod="15m",
                 exitSigPeriod="15m",
                 ):
        # 根据出场信号出场
        exitSig = self.exitSignal(period=exitSigPeriod)
        self.exitOrder(exitSig)

        # 根据进场信号进场
        entrySig = self.entrySignal(period=entrySigPeriod)
        if entrySig != 0:  # 有下单信号
            if not self.isTrendEnv(trendPeriod) and self.haveEnoughVol(volPeriod):  # 当前不是趋势环境且有足够的波动空间
                self.entryOrder(entrySig, marketPrice)  # 进场

        # 更新记录am中最新一根K线的时间
        self.updateLastBarTime()

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

    # 判断当前大环境是否是趋势环境
    def isTrendEnv(self, period="1h"):
        am = self.getArrayManager(self.symbol, period)
        if not am.inited:
            self.writeCtaLog("am is not inited:%s" % (period,))
            return True
        return ENVIRONMENT.isTrendbyADX(am, ADXLen=self.ADXLen, ADXThreshold=self.ADXThreshold)

    # 判断是否有足够的波动空间
    def haveEnoughVol(self, period="15m"):
        am = self.getArrayManager(self.symbol, period)
        if not am.inited:
            self.writeCtaLog("am is not inited:%s" % (period,))
            return False
        return ENVIRONMENT.haveEnoughVolbyATR(am, ATRLen=self.ATRLen, ATRMALen=self.ATRMALen,
                                              minATRLimit=self.minATRLimit)

    # 平仓信号
    def exitSignal(self, period="15m"):
        sig = 0
        barPrepared, am = self.barPrepared(period)
        if barPrepared:
            sig = CLOSESIGNAL.closebyPriceVolumeReverse(am, corrLen=self.corrLen,
                                                        exitCorrLong=self.exitCorrLong,
                                                        exitCorrLongRange=self.exitCorrLongRange)
        return sig

    # 开仓信号
    def entrySignal(self, period="15m"):
        sig = 0
        barPrepared, am = self.barPrepared(period)
        if barPrepared:
            sig = OPENSIGNAL.openbyPriceVolumeReverse(
                am,
                corrLen=self.corrLen,
                posRange=self.posRange, negDirPctRange=self.negDirPctRange, sameDirPctLimit=self.sameDirPctLimit,
                minCorrLong1=self.minCorrLong1, minCorrLong2=self.minCorrLong2, minCorrShort1=self.minCorrShort1,
                holdingBuyOP=(len(self.orderDict["buy"]) > 0), holdingShortOP=(len(self.orderDict["short"]) > 0)
            )
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

    # 下单进场,指定止盈止损和到时间出场
    def entryOrder(self, sig, price):
        if sig > 0:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_BUY, self.symbol, price * 1.001, self.lot,
                                      self.orderWaitingTime)
            for orderID in tlo.vtOrderIDs:
                # 将订单ID加到集合
                self.orderDict["buy"].add(orderID)
                op = self._orderPacks[orderID]
                self.setAutoExit(op, price * (1 - self.stopLoss),
                                 price * (1 + self.takeProfit))  # 设置止盈止损
                self.setConditionalClose(op, self.holdWaitingTime, self.expectedReturn)
        if sig < 0:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_SHORT, self.symbol, price * 0.999, self.lot,
                                      self.orderWaitingTime)

            for orderID in tlo.vtOrderIDs:
                # 将订单ID加到集合
                self.orderDict["short"].add(orderID)
                op = self._orderPacks[orderID]
                self.setAutoExit(op, price * (1 + self.stopLoss),
                                 price * (1 - self.takeProfit))
                self.setConditionalClose(op, self.holdWaitingTime, self.expectedReturn)