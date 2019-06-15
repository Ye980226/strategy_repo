from vnpy.trader.vtConstant import *
import numpy as np
import talib as ta
from datetime import timedelta, datetime
from vnpy.trader.utils.templates.orderTemplate import * 
from vnpy.trader.app.ctaStrategy import ctaBase
from candleClass import candleSignal


########################################################################
class outsideCandleStrategy(OrderTemplate):
    className = 'outsideCandleStrategy'
    author = 'ChannelCMT'

    # 参数列表，保存了参数的名称
    paramList = [
                 # 分批进场手数
                 'lot',
                 # 品种列表
                 'symbolList',
                 # 趋势方向参数
                 'rsiPeriod',
                 'rsiUpThreshold', 'rsiDnThreshold',
                 # 信号参数
                 "volumeMaPeriod", "volumeStdMultiple",
                 'hlPct', 'cPct',
                 # 止损止盈参数
                 "takeProfitPct", "stopLossPct",
                 "holdTime", "holdTimeAdd","expectReturn",
                 "addPct",
                 "posTime","addMultipler",
                 # 时间周期
                 'timeframeMap',
                 #  总秒，间隔，下单次数
                 'totalSecond', 'stepSecond','orderTime'
                 ]

    # 变量列表，保存了变量的名称
    varList = [
               'nPos'
               ]

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)

        self.paraDict = setting
        self.barPeriod = 600
        engineType = self.getEngineType()  # 判断engine模式
        self.symbol = self.symbolList[0]
        self.nPos = 0

        # varialbes
        self.orderDict = {'orderLongSet':set(), 'orderShortSet': set()}
        self.initOrderList = []
        # 打印全局信号的字典
        self.globalStatus = {}
        self.chartLog = {
                        'datetime':[],
                        'rsi': [],
                        'volume': [],
                        'volumeUpper': [],
                        }
    
    def prepare_data(self):
        for timeframe in list(set(self.timeframeMap.values())):
            self.registerOnBar(self.symbol, timeframe, None)

    def arrayPrepared(self, period):
        am = self.getArrayManager(self.symbol, period)
        if not am.inited:
            return False, None
        else:
            return True, am

    # ----------------------------------------------------------------------
    def onInit(self):
        self.setArrayManagerSize(self.barPeriod)
        self.prepare_data()
        self.mail("chushihuaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.putEvent()
    
    # ----------------------------------------------------------------------
    def onStart(self):
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        self.putEvent()

    # 定时清除已经出场的单
    def delOrderID(self, orderSet):
        for orderId in list(orderSet):
            op = self._orderPacks[orderId]
            # 检查是否完全平仓
            if self.orderClosed(op):
                # 在记录中删除
                orderSet.discard(orderId)
    
    def moveStopLoss(self, bar, orderSet):
        for orderId in list(orderSet):
            op = self._orderPacks[orderId]
            # 通过改一张单绑定的AutoExitInfo属性修改止损止盈
            if self.isAutoExit(op):
                ae = op.info[AutoExitInfo.TYPE]
                sl = op.info['slGap']
                if op.order.direction == constant.DIRECTION_LONG:
                    if (bar.high - ae.stoploss) >= 2 * sl:
                        self.setAutoExit(op, op.order.price_avg*1.005)
                elif op.order.direction == constant.DIRECTION_SHORT:
                    if (ae.stoploss - bar.low) >= 2 * sl:
                        self.setAutoExit(op, op.order.price_avg*0.995)

    # 获得执行价格
    def priceExecute(self, bar):
        if bar.vtSymbol in self._tickInstance:
            tick = self._tickInstance[bar.vtSymbol]
            if tick.datetime >= bar.datetime:
                return tick.upperLimit * 0.99, tick.lowerLimit*1.01
        return bar.close*1.02, bar.close*0.98


    # 获取当前的持有仓位
    def getHoldVolume(self, orderSet):
        pos = 0
        for orderID in orderSet:
            op = self._orderPacks[orderID]
            holdVolume = op.order.tradedVolume
            closedVolume = self.orderClosedVolume(op)
            pos+= (holdVolume-closedVolume)
        return pos
    
    # 实盘在5sBar中洗价
    def on5sBar(self, bar):
        self.checkOnPeriodStart(bar)
        self.checkOnPeriodEnd(bar)
        for idSet in self.orderDict.values():
            self.delOrderID(idSet)

    def onBar(self, bar):
        # 必须继承父类方法
        super().onBar(bar)
        # on bar下触发回测洗价逻辑
        engineType = self.getEngineType()  # 判断engine模式
        if engineType == 'backtesting':
            # 定时控制，开始
            self.checkOnPeriodStart(bar)
            # 回测时的下单手数按此方法调整
            self.lot = int(200000 / bar.close)
        # 定时清除已出场的单
            self.checkOnPeriodStart(bar)
            self.checkOnPeriodEnd(bar)

            for idSet in self.orderDict.values():
                self.delOrderID(idSet)
                # self.moveStopLoss(bar, idSet)
        # 执行策略逻辑
        self.strategy(bar)

    def on5MinBar(self, bar):
        engineType = self.getEngineType()  # 判断engine模式
        if engineType != 'backtesting':
            self.writeCtaLog('globalStatus%s'%(self.globalStatus))
            self.writeCtaLog('longVolume:%s, shortVolume:%s'%(self.getHoldVolume(self.orderDict['orderLongSet']), self.getHoldVolume(self.orderDict['orderShortSet'])))
            self.notifyPosition('longVolume', self.getHoldVolume(self.orderDict['orderLongSet']), 'ChannelPos')
            self.notifyPosition('shortVolume', self.getHoldVolume(self.orderDict['orderShortSet']), 'ChannelPos')

    def strategy(self, bar):
        signalPeriod = self.timeframeMap["signalPeriod"]
        candlePeriod = self.timeframeMap["candlePeriod"]

        # 根据出场信号出场
        exitSig = self.exitSignal(signalPeriod)
        self.exitOrder(exitSig)

        # 根据进场信号进场
        entrySig = self.entrySignal(signalPeriod, candlePeriod)
        self.entryOrder(bar, entrySig)

        self.addPosOrder(bar)

    def exitSignal(self, signalPeriod):
        exitSignal = 0
        arrayPrepared, amSignal = self.arrayPrepared(signalPeriod)

        algorithm = candleSignal()
        # or trendDirection==-1  or (k[-1]<d[-1] and k[-2]>=d[-2]) k[-1]>=85
        #  or trendDirection==1or (k[-1]>d[-1] and k[-2]<=d[-2]) k[-1]<=15
        # if arrayPrepared1:
        #     trendDirection, trendSma, trendLma = algorithm.maSignal(amTrend, self.paraDict)
        #     k, d = algorithm.kdjSignal(amSignal, self.paraDict)
        #     if k[-1]>=65 and (k[-1]<d[-1] and k[-2]>=d[-2]):
        #         exitSignal = 1
        #     elif k[-1]<=35 and (k[-1]>d[-1] and k[-2]<=d[-2]):
        #         exitSignal = -1
        #     else:
        #         exitSignal = 0
        return exitSignal
    
    def exitOrder(self, exitSignal):
        if exitSignal == 1:
            for orderID in (self.orderDict['orderLongSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)
        elif exitSignal==-1:
            for orderID in (self.orderDict['orderShortSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)

    def entrySignal(self, signalPeriod, candlePeriod):
        entrySignal = 0
        arrayPrepared1, amSignal = self.arrayPrepared(signalPeriod)
        arrayPrepared2, amCandle = self.arrayPrepared(candlePeriod)
        arrayPrepared = arrayPrepared1 and arrayPrepared2
        
        algorithm = candleSignal()        
        if arrayPrepared:
            rsiStatus, rsi = algorithm.rsiSignal(amSignal, self.paraDict)
            volumeSpike, volumeUpper = algorithm.volumeSignal(amCandle, self.paraDict)    
            candleDirection = algorithm.candleSignal(amCandle, self.paraDict)

            self.globalStatus['rsiStatus'] = rsiStatus
            self.globalStatus['rsi'] = rsi[-1]
            self.globalStatus['volumeSpike'] = volumeSpike
            self.globalStatus['volumeUpper'] = volumeUpper[-1]
            self.globalStatus['candleDirection'] = candleDirection

            self.chartLog['datetime'].append(datetime.strptime(amCandle.datetime[-1], "%Y%m%d %H:%M:%S"))
            self.chartLog['rsi'].append(rsi[-1])
            self.chartLog['volume'].append(amCandle.volume[-1])
            self.chartLog['volumeUpper'].append(volumeUpper[-1])

            if (rsiStatus == 1) and (volumeSpike==1) and (candleDirection==1):
                entrySignal = 1
            elif (rsiStatus == -1) and (volumeSpike==1) and (candleDirection==-1):
                entrySignal = -1
            else:
                entrySignal = 0
        return entrySignal

    def entryOrder(self, bar, entrySignal):
        buyExecute, shortExecute = self.priceExecute(bar)
        if entrySignal ==1:
            if not self.orderDict['orderLongSet']:
                # 如果回测直接下单，如果实盘就分批下单
                for orderID in self.timeLimitOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, self.lot, 120).vtOrderIDs:
                    self.orderDict['orderLongSet'].add(orderID)
                    op = self._orderPacks[orderID]
                    self.setConditionalClose(op, self.holdTime)
                    self.initOrderList.append(orderID)

        elif entrySignal ==-1:
            if not self.orderDict['orderShortSet']:
                for orderID in self.timeLimitOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, self.lot, 120).vtOrderIDs:
                    self.orderDict['orderShortSet'].add(orderID)
                    op = self._orderPacks[orderID]
                    self.setConditionalClose(op, self.holdTime)
                    self.initOrderList.append(orderID)

    def addPosOrder(self, bar):
        buyExecute, shortExecute = self.priceExecute(bar)
        if not (self.orderDict['orderLongSet'] or self.orderDict['orderShortSet']):
            self.nPos = 0
            self.initOrderList = []
        elif len(self.initOrderList):
            opID = self.initOrderList[0]
            op = self._orderPacks[opID]
            firstOrder = op.order.price_avg
            if self.isAutoExit(op):
                ae = op.info[AutoExitInfo.TYPE]
                slGap = op.info["slGap"]
                if op.order.direction == constant.DIRECTION_LONG and (self.nPos < self.posTime):
                    if (firstOrder / bar.close - 1) >= (self.nPos+1)*self.addPct:
                        self.nPos += 1
                        addPosLot = int(self.lot * (self.addMultipler ** self.nPos))
                        for orderID in self.timeLimitOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute,
                                                            addPosLot, 60).vtOrderIDs:
                            addOp = self._orderPacks[orderID]
                            addOp.info["slGap"] = slGap
                            self.setAutoExit(addOp, ae.stoploss, ae.takeprofit)
                            self.orderDict['orderLongSet'].add(orderID)
                            # op = self._orderPacks[orderID]
                            # self.setConditionalClose(op, self.holdTimeAdd, self.expectReturn)                  
                elif op.order.direction == constant.DIRECTION_SHORT and (self.nPos < self.posTime):
                    if (bar.close / firstOrder - 1) >= (self.nPos+1)*self.addPct:
                        self.nPos += 1
                        addPosLot = int(self.lot * (self.addMultipler ** self.nPos))
                        for orderID in self.timeLimitOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute,
                                                            addPosLot, 60).vtOrderIDs:
                            addOp = self._orderPacks[orderID]
                            addOp.info["slGap"] = slGap
                            self.setAutoExit(addOp, ae.stoploss, ae.takeprofit)
                            self.orderDict['orderShortSet'].add(orderID)
                            # op = self._orderPacks[orderID]
                            # self.setConditionalClose(op, self.holdTimeAdd, self.expectReturn)


    # ----------------------------------------------------------------------
    def onOrder(self, order):
        super().onOrder(order)
        if order.status == STATUS_UNKNOWN:
            self.mail(u'出现未知订单，需要策略师外部干预,ID:%s, symbol:%s,direction:%s,offset:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))
        if order.status == STATUS_REJECTED:
            self.mail(u'Rejected,ID:%s, symbol:%s,direction:%s,offset:%s,拒单信息:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset,order.rejectedInfo))
        if order.thisTradedVolume != 0:
            content = u'成交信息播报,ID:%s, symbol:%s, directionL%s, offset:%s, price:%s'%\
                      (order.vtOrderID, order.vtSymbol, order.direction, order.offset, order.price_avg)
            self.mail(content)
        self.setStop(order)

    def setStop(self, order):
        op = self._orderPacks.get(order.vtOrderID, None)
        # 判断是否该策略下的开仓
        if op:
            # 如果没有加过仓就设置初始的止损止盈
            if order.offset == constant.OFFSET_OPEN:
                if self.nPos==0 and order.price_avg!=0:
                    slGap = order.price_avg*self.stopLossPct
                    tpGap = order.price_avg*self.takeProfitPct
                    if order.direction == constant.DIRECTION_LONG:
                        if op.vtOrderID in self.orderDict['orderLongSet']:
                            self.setAutoExit(op, (order.price_avg-slGap), order.price_avg+tpGap)
                            op.info['slGap'] = slGap
                            self.globalStatus['orderLongGap'] = {'SL': order.price_avg-slGap, 'TP': order.price_avg+tpGap}
                    elif order.direction == constant.DIRECTION_SHORT:
                        if op.vtOrderID in self.orderDict['orderShortSet']:
                            self.setAutoExit(op, (order.price_avg+slGap), order.price_avg-tpGap)
                            op.info['slGap'] = slGap                            
                            self.globalStatus['orderFirstShort'] = {'SL': order.price_avg+slGap, 'TP': order.price_avg-tpGap}

    # ----------------------------------------------------------------------
    # 成交后用成交价设置第一张止损止盈
    def onTrade(self, trade):
        pass

    def onStopOrder(self, so):
        pass