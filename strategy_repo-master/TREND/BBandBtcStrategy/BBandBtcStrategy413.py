from vnpy.trader.vtConstant import *
import numpy as np
import talib as ta
from datetime import timedelta, datetime
from vnpy.trader.utils.templates.orderTemplate import * 
from vnpy.trader.app.ctaStrategy import ctaBase
from BBandSignalClass import BBandSignal
########################################################################
class BBandBreakStrategy(OrderTemplate):
    className = 'BBandBreak'
    author = 'ChannelCMT'

    # 参数列表，保存了参数的名称
    paramList = [
                 # 进场手数
                 'lot',
                 # 品种列表
                 'symbolList',
                 # envParameter 计算ADX环境的参数
                 'adxPeriod', 'adxLowthreshold',
                 'adxHighthreshold','adxMaxPeriod',
                 # signalParameter 计算信号的参数
                 'bBandShortPeriod','bBandLongPeriod',
                 'bBandEntry','bBandExit',
                 # 出场后停止的小时
                 'stopControlTime',
                 # 波动率过滤阈值
                 'volPeriod','highVolthreshold', 'lowVolthreshold',
                 # 加仓信号指标
                 'lotMultipler',
                 # 价格变化百分比加仓， 加仓的乘数
                 'addPct','addMultipler',
                 # 可加仓的次数
                 'posTime',
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
        self.barPeriod = 500
        self.symbol = self.symbolList[0]

        # varialbes
        self.orderDict = {'orderLongSet':set(), 'orderShortSet':set()}
        self.orderLastList = []
        self.lastOrderDict = {'nextExecuteTime': datetime(2000, 1, 1)}
        self.nPos = 0

        # 打印全局信号的字典
        self.globalStatus = {}

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
                self.lastOrderDict['nextExecuteTime'] = self.currentTime + timedelta(hours=self.stopControlTime)
    
    # 获得执行价格
    def priceExecute(self, bar):
        if bar.vtSymbol in self._tickInstance:
            tick = self._tickInstance[bar.vtSymbol]
            if tick.datetime >= bar.datetime:
                return tick.upperLimit * 0.99, tick.lowerLimit*1.01
        return bar.close*1.02, bar.close*0.98

    def getHoldVolume(self, orderSet):
        pos = 0
        for orderID in orderSet:
            op = self._orderPacks[orderID]
            holdVolume = op.order.tradedVolume
            pos+= holdVolume
        return pos

    # 实盘在5sBar中洗价,并且在5sBar下执行出场
    def on5sBar(self, bar):
        self.checkOnPeriodStart(bar)
        self.checkOnPeriodEnd(bar)
        for idSet in self.orderDict.values():
            self.delOrderID(idSet)
        # 执行策略逻辑
        self.strategy(bar)

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
        envPeriod= self.timeframeMap["envPeriod"]
        filterPeriod= self.timeframeMap["filterPeriod"]
        signalPeriod= self.timeframeMap["signalPeriod"]
        tradePeriod= self.timeframeMap["tradePeriod"]
        addPosPeriod = self.timeframeMap["addPosPeriod"]
                
        # 根据出场信号出场
        bBandShortExitUp, bBandShortExitDn , bBandLongExitUp, bBandLongExitDn = self.exitSignal(signalPeriod)
        self.exitOrder(bar, bBandShortExitUp, bBandShortExitDn , bBandLongExitUp, bBandLongExitDn)

        # 根据进场信号进场
        entrySig = self.entrySignal(envPeriod, filterPeriod, signalPeriod, tradePeriod)
        self.entryOrder(bar, entrySig)

        # 根据信号加仓
        self.addPosOrder(bar)

    def isStopControled(self):
        return self.currentTime < self.lastOrderDict['nextExecuteTime']

    def exitSignal(self, signalPeriod):
        bBandShortExitUp, bBandShortExitDn , bBandLongExitUp, bBandLongExitDn = np.array([]), np.array([]), np.array([]), np.array([])
        arrayPrepared1, amSignal = self.arrayPrepared(signalPeriod)
        algorithm = BBandSignal()
        if arrayPrepared1:
            bBandShortExitUp, bBandShortExitDn , bBandLongExitUp, bBandLongExitDn = algorithm.bBandExitSignal(amSignal, self.paraDict)
        return bBandShortExitUp, bBandShortExitDn , bBandLongExitUp, bBandLongExitDn
    
    def exitOrder(self, bar, bBandShortExitUp, bBandShortExitDn , bBandLongExitUp, bBandLongExitDn):
        if not (len(bBandShortExitDn) or len(bBandShortExitDn) or len(bBandLongExitUp) or len(bBandLongExitDn)):
            return
        exitLongTouchLowest = (bar.low<bBandShortExitDn[-1]) or (bar.low<bBandLongExitDn[-1])
        exitShortTouchHighest = (bar.high>bBandShortExitUp[-1]) or (bar.high>bBandLongExitUp[-1])
        if exitLongTouchLowest:
            for orderID in (self.orderDict['orderLongSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)
        elif exitShortTouchHighest:
            for orderID in (self.orderDict['orderShortSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)

    def entrySignal(self, envPeriod, filterPeriod, signalPeriod, tradePeriod):
        entrySignal = 0
        arrayPrepared1, amEnv = self.arrayPrepared(envPeriod)
        arrayPrepared2, amFilter = self.arrayPrepared(filterPeriod)
        arrayPrepared3, amSignal = self.arrayPrepared(signalPeriod)
        arrayPrepared4, amTrade = self.arrayPrepared(tradePeriod)
        arrayPrepared = arrayPrepared1 and arrayPrepared2 and arrayPrepared3 and arrayPrepared4
        algorithm = BBandSignal()        
        if arrayPrepared:
            adxCanTrade, adxTrend = algorithm.adxEnv(amEnv, self.paraDict)
            filterCanTrade, highVolPos = algorithm.fliterVol(amFilter, self.paraDict)
            bBandShortEntryUp, bBandShortEntryMa, bBandShortEntryDn, bBandLongEntryUp, bBandLongEntryMa, bBandLongEntryDn = algorithm.bBandEntrySignal(amSignal, self.paraDict)
            breakHighest = (amTrade.close[-1]>bBandShortEntryUp[-1]) and (amTrade.close[-1]>bBandLongEntryUp[-1]) and bBandShortEntryMa[-1]>bBandLongEntryMa[-1]
            breakLowest = (amTrade.close[-1]<bBandShortEntryDn[-1]) and (amTrade.close[-1]<bBandLongEntryDn[-1]) and bBandShortEntryMa[-1]<bBandLongEntryMa[-1]
            self.globalStatus['adxCanTrade'] = adxCanTrade
            self.globalStatus['filterCanTrade'] = filterCanTrade
            self.globalStatus['breakHighest'] = breakHighest
            self.globalStatus['breakLowest'] = breakLowest
            self.globalStatus['highVolPos'] = highVolPos
            self.globalStatus['adxTrend'] = adxTrend[-1]
            self.globalStatus['bBandLongEntryUp'] = bBandLongEntryUp[-1]
            self.globalStatus['bBandLongEntryDn'] = bBandLongEntryDn[-1]
            self.globalStatus['bBandShortEntryUp'] = bBandShortEntryUp[-1]
            self.globalStatus['bBandShortEntryDn'] = bBandShortEntryDn[-1]

            if highVolPos:
                self.lotMultipler = 0.5
            else:
                self.lotMultipler = 1

            if (adxCanTrade == 1) and (filterCanTrade == 1):
                if not self.isStopControled():
                    if breakHighest:
                        entrySignal = 1
                    elif breakLowest:
                        entrySignal = -1
        return entrySignal

    def entryOrder(self, bar, entrySignal):
        engineType = self.getEngineType()  # 判断engine模式
        buyExecute, shortExecute = self.priceExecute(bar)
        lotSize = self.lot * self.lotMultipler
        if entrySignal ==1:
            if not self.orderDict['orderLongSet']:
                # 如果回测直接下单，如果实盘就分批下单
                longPos = self.lot//self.orderTime
                    # for orderID in self.timeLimitOrder(ctaBase.CTAORDER_BUY, self.symbol, buyExecute, self.lot, 120).vtOrderIDs:
                stepOrder = self.makeStepOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, self.lot, longPos, self.totalSecond, self.stepSecond)                 
                orderID = stepOrder.parentID
                self.orderDict['orderLongSet'].add(orderID)
                self.orderLastList.append(orderID)

        elif entrySignal ==-1:
            if not self.orderDict['orderShortSet']:
                    # for orderID in self.timeLimitOrder(ctaBase.CTAORDER_SHORT, self.symbol, shortExecute, self.lot, 120).vtOrderIDs:
                shortPos = self.lot//self.orderTime
                stepOrder = self.makeStepOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, self.lot, shortPos, self.totalSecond, self.stepSecond)
                orderID = stepOrder.parentID                
                self.orderDict['orderShortSet'].add(orderID)
                self.orderLastList.append(orderID)

    # 计算可加仓的信号
   # 通过上一张单来设置止损止盈
    def addPosOrder(self, bar):
        buyExecute, shortExecute = self.priceExecute(bar)
        if not (self.orderDict['orderLongSet'] or self.orderDict['orderShortSet']):
            self.nPos = 0
            self.orderLastList = []
        else:
            lastOrderID = self.orderLastList[-1]
            op = self._orderPacks[lastOrderID]
            lastOrder = op.order.price_avg
            if lastOrder!=0:
                if op.order.direction == constant.DIRECTION_LONG and (self.nPos < self.posTime):
                    if ((bar.close/lastOrder - 1) >= self.addPct) and ((bar.close/lastOrder - 1)<=2*self.addPct):
                        self.nPos += 1
                        addPosLot = int(self.lotMultipler* self.lot * (self.addMultipler**self.nPos))
                        for orderID in self.timeLimitOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, addPosLot, 60).vtOrderIDs:
                            self.globalStatus['addPos'] = (self.nPos, addPosLot)
                            self.orderLastList.append(orderID)
                            addOp = self._orderPacks[orderID]
                            self.orderDict['orderLongSet'].add(orderID)                    
                elif op.order.direction == constant.DIRECTION_SHORT and (self.nPos < self.posTime):
                    if ((lastOrder/bar.close - 1) >= self.addPct) and ((lastOrder/bar.close - 1) <= 2*self.addPct):
                        self.nPos += 1
                        addPosLot = int(self.lotMultipler*self.lot*(self.addMultipler**self.nPos))
                        for orderID in self.timeLimitOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, addPosLot, 60).vtOrderIDs:
                            self.globalStatus['addPos'] = (self.nPos, addPosLot)
                            self.orderLastList.append(orderID)
                            addOp = self._orderPacks[orderID]
                            self.orderDict['orderShortSet'].add(orderID)                                    

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        super().onOrder(order)
        op = self._orderPacks[order.vtOrderID]
        if not self.isFake(op):
            if order.status == STATUS_UNKNOWN:
                self.mail(u'出现未知订单，需要策略师外部干预,ID:%s, symbol:%s,direction:%s,offset:%s'
                        % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))
            if order.status == STATUS_REJECTED:
                self.mail(u'Rejected,ID:%s, symbol:%s,direction:%s,offset:%s,拒单信息:%s'
                        % (order.vtOrderID, order.vtSymbol, order.direction, order.offset,order.rejectedInfo))
            if order.thisTradedVolume != 0:
                if order.status in STATUS_FINISHED:
                    content = u'成交信息播报,ID:%s, symbol:%s, directionL%s, offset:%s, price:%s, tradedVolume:%s'%\
                            (order.vtOrderID, order.vtSymbol, order.direction, order.offset, order.price_avg, order.tradedVolume)
                # self.mail(content)

    # ----------------------------------------------------------------------
    # 成交后用成交价设置第一张止损止盈
    def onTrade(self, trade):
        pass

    def onStopOrder(self, so):
        pass