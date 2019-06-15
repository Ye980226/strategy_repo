from vnpy.trader.vtConstant import *
import numpy as np
import talib as ta
import pandas as pd
from datetime import timedelta, datetime
from vnpy.trader.utils.templates.orderTemplate import * 
from vnpy.trader.app.ctaStrategy import ctaBase
from hlBreakSignalClass import hlBreakSignal

########################################################################
class hlBreakStrategy(OrderTemplate):
    className = 'hlBreak'
    author = 'ChannelCMT'

    # 参数列表，保存了参数的名称
    paramList = [
                 # 进场手数
                 'lot',
                 # 品种列表
                 'symbolList',
                 # envParameter 计算ADX环境的参数
                 'adxPeriod', 'adxLowThreshold',
                 'adxHighThreshold','adxMaxPeriod',
                 # signalParameter 计算信号的参数
                 'hlEntryPeriod','hlExitPeriod',
                 # 出场后停止的小时
                 'stopControlTime',
                 # 波动率过滤阈值
                 'volPeriod','highVolThreshold', 'lowVolThreshold',
                 # 加仓信号指标
                 'erThreshold','changeVolatilityPeriod',
                 'erSemaPeriod', 'erLemaPeriod',
                 # 价格变化百分比加仓， 加仓的乘数
                 'addPct','addMultipler','lotMultipler',
                 # 可加仓的次数
                 'posTime',
                 # 时间周期
                 'timeframeMap',
                 'barCount', 'volumePeriod', 'volumeSpikeTime', 'priceSpikePct',
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
        self.orderDict = {
                          'orderLongSet':set(), 'orderShortSet':set(),
                          'orderLongAddSet':set(), 'orderShortAddSet':set()
                         }
        self.orderLastList = []
        self.lastOrderDict = {'nextExecuteTime': datetime(2000, 1, 1)}
        self.addExitTime =  {'addExitLongTime': datetime(2000, 1, 1),
                             'addExitShortTime': datetime(2000, 1, 1),
                            }
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

    # 获取当前的持有仓位
    def getHoldVolume(self, orderSet):
        pos = 0
        for orderID in orderSet:
            op = self._orderPacks[orderID]
            holdVolume = op.order.tradedVolume
            pos+= holdVolume
        return pos

    # 实盘在5sBar中洗价
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
        highExitBand, lowExitBand, spikeStatus = self.exitSignal(envPeriod, signalPeriod)
        if len(highExitBand) and len(lowExitBand):
            self.exitOrder(bar, highExitBand, lowExitBand, spikeStatus)
        
        # 根据进场信号进场
        entrySig = self.entrySignal(envPeriod, filterPeriod, signalPeriod, tradePeriod)
        self.entryOrder(bar, entrySig)

        # 根据信号加仓
        addPosSig = self.addPosSignal(addPosPeriod)
        self.addPosOrder(bar, addPosSig)

    def isStopControled(self):
        return self.currentTime < self.lastOrderDict['nextExecuteTime']

    def holdAddTimeDone(self):
        holdAddDone = 0
        if len(self.orderDict['orderLongAddSet']):
            holdAddDone = self.currentTime > self.addExitTime['addExitLongTime']
        elif len(self.orderDict['orderShortAddSet']):
            holdAddDone = self.currentTime > self.addExitTime['addExitShortTime']
        return holdAddDone

    def exitSignal(self, envPeriod, signalPeriod):
        highExitBand, lowExitBand = np.array([]) , np.array([])
        spikeStatus = 0
        arrayPrepared1, amEnv = self.arrayPrepared(envPeriod)
        arrayPrepared2, amSignal = self.arrayPrepared(signalPeriod)
        algorithm = hlBreakSignal()
        if arrayPrepared1 and arrayPrepared2:
            adxCanTrade, adxTrend = algorithm.adxEnv(amEnv, self.paraDict)
            if adxCanTrade ==1:
                highExitBand, lowExitBand = algorithm.hlExitWideBand(amSignal, self.paraDict)
            else:
                highExitBand, lowExitBand = algorithm.hlExitNorrowBand(amSignal, self.paraDict)
            spikeStatus = algorithm.hlcVolumeSpike(amSignal, self.paraDict)
        return highExitBand, lowExitBand, spikeStatus

    def exitOrder(self, bar, highExitBand, lowExitBand, spikeStatus):
        exitLongTouchLowest = (bar.low<lowExitBand[-2])
        exitShortTouchHighest = (bar.high>highExitBand[-2])
        holdAddTime = self.holdAddTimeDone()

        # if spikeStatus=='exitLong' and holdAddTime:
        #     for orderID in (self.orderDict['orderLongAddSet']):
        #         op = self._orderPacks[orderID]
        #         self.composoryClose(op)
        # elif spikeStatus=='exitShort' and holdAddTime:
        #     for orderID in (self.orderDict['orderShortAddSet']):
        #         op = self._orderPacks[orderID]
        #         self.composoryClose(op)

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
        algorithm = hlBreakSignal()
        if arrayPrepared:
            adxCanTrade, adxTrend = algorithm.adxEnv(amEnv, self.paraDict)
            filterCanTrade, highVolPos = algorithm.fliterVol(amFilter, self.paraDict)
            if adxCanTrade ==1:
                highEntryBand, lowEntryBand = algorithm.hlEntryNorrowBand(amSignal, self.paraDict)
                filterVCanTrade = algorithm.filterNorrowPatternV(amSignal, self.paraDict)            
            else:
                highEntryBand, lowEntryBand = algorithm.hlEntryWideBand(amSignal, self.paraDict)
                filterVCanTrade = algorithm.filterWidePatternV(amSignal, self.paraDict)
            breakHighest = (amTrade.close[-1]>highEntryBand[-2]) and (amTrade.close[-2]<=highEntryBand[-2])
            breakLowest = (amTrade.close[-1]<lowEntryBand[-2]) and (amTrade.close[-2]>=lowEntryBand[-2])
            
            self.globalStatus['adxCanTrade'] = adxCanTrade
            self.globalStatus['filterCanTrade'] = filterCanTrade
            self.globalStatus['breakHighest'] = breakHighest
            self.globalStatus['breakLowest'] = breakLowest
            self.globalStatus['adxTrend'] = adxTrend[-1]
            self.globalStatus['highEntryBand'] = highEntryBand[-1]
            self.globalStatus['lowEntryBand'] = lowEntryBand[-1]

            if highVolPos:
                self.lotMultipler = 0.5
            else:
                self.lotMultipler = 1

            if (adxCanTrade == 1) and (filterCanTrade == 1) and (filterVCanTrade==1):
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
    def addPosSignal(self, addPosPeriod):
        erCanAddPos = 1
        # arrayPrepared, amAddPos = self.arrayPrepared(addPosPeriod)
        # if arrayPrepared:
        #     algorithm = hlBreakSignal()
        #     erCanAddPos, erSma, erLma = algorithm.erAdd(amAddPos, self.paraDict)
        return erCanAddPos

    # 通过上一张单来设置止损止盈
    def addPosOrder(self, bar, addPosSignal):
        buyExecute, shortExecute = self.priceExecute(bar)
        if not (self.orderDict['orderLongSet'] or self.orderDict['orderShortSet']):
            self.nPos = 0
            self.orderLastList = []
        else:
            lastOrderID = self.orderLastList[-1]
            op = self._orderPacks[lastOrderID]
            lastOrder = op.order.price_avg
            if lastOrder!=0:
                if addPosSignal:
                    if op.order.direction == constant.DIRECTION_LONG and (self.nPos < self.posTime):
                        if ((bar.close/lastOrder - 1) >= self.addPct) and ((bar.close/lastOrder - 1)<=2*self.addPct):
                            self.nPos += 1
                            addPosLot = int(self.lotMultipler* self.lot * (self.addMultipler**self.nPos))
                            for orderID in self.timeLimitOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, addPosLot, 60).vtOrderIDs:
                                self.globalStatus['addPos'] = (self.nPos, addPosLot)
                                self.orderLastList.append(orderID)
                                addOp = self._orderPacks[orderID]
                                self.orderDict['orderLongSet'].add(orderID)
                                self.orderDict['orderLongAddSet'].add(orderID)
                                self.addExitTime['addExitLongTime'] =  self.currentTime+timedelta(minutes=self.barCount*15)
                    elif op.order.direction == constant.DIRECTION_SHORT and (self.nPos < self.posTime):
                        if ((lastOrder/bar.close - 1) >= self.addPct) and ((lastOrder/bar.close - 1) <= 2*self.addPct):
                            self.nPos += 1
                            addPosLot = int(self.lotMultipler*self.lot*(self.addMultipler**self.nPos))
                            for orderID in self.timeLimitOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, addPosLot, 60).vtOrderIDs:
                                self.globalStatus['addPos'] = (self.nPos, addPosLot)
                                self.orderLastList.append(orderID)
                                addOp = self._orderPacks[orderID]
                                self.orderDict['orderShortSet'].add(orderID)
                                self.orderDict['orderShortAddSet'].add(orderID)
                                self.addExitTime['addExitShortTime'] =  self.currentTime+timedelta(minutes=self.barCount*15)

 # ----------------------------------------------------------------------
    def onOrder(self, order):
        super().onOrder(order)
    pass

    # ----------------------------------------------------------------------
    # 成交后用成交价设置第一张止损止盈
    def onTrade(self, trade):
        pass

    def onStopOrder(self, so):
        pass