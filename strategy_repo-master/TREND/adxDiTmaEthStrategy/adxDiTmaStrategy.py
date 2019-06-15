from vnpy.trader.vtConstant import *
import numpy as np
import talib as ta
from datetime import timedelta, datetime
from vnpy.trader.utils.templates.orderTemplate import * 
from vnpy.trader.app.ctaStrategy import ctaBase
from adxDiTmaClass import adxDiTmaSignal

########################################################################
class adxDiTmaStrategy(OrderTemplate):
    className = 'adxDi'
    author = 'ChannelCMT'

    # 参数列表，保存了参数的名称
    paramList = [
                 # 分批进场手数
                 'lot1', 'lot2',
                 # 品种列表
                 'symbolList',
                 # envParameter 计算ADX环境的参数
                 'adxPeriod', 'adxMaPeriod', 'adxMaType', 'adxThreshold',
                 # signalParameter 计算信号的参数
                 'smaPeriod','smaType', 'lmaPeriod','envMaPeriod',
                 # 追踪止损的百分比
                 'trailingPct', 
                 # 出场后停止的小时
                 'stopControlTime',
                 # 价格变化百分比加仓， 加仓的乘数
                 'addPct','addMultipler',
                 # 低波动率过滤阈值
                 'volPeriod', 'lowVolThreshold',
                 # 分批止盈价格 
                 'takeProfitFirstPct', 'takeProfitSecondPct',
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
        engineType = self.getEngineType()  # 判断engine模式
        self.symbol = self.symbolList[0]

        # varialbes
        self.orderDict = {
                          'orderFirstLongSet':set(), 'orderSecondLongSet': set(),
                          'orderFirstShortSet':set(), 'orderSecondShortSet': set(),
                         }
        self.orderAllList = []
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

    def modifyStopLoss(self, bar, orderSet):
        modify = 0
        if len(self.orderAllList)>0:
            lastOrderId = self.orderAllList[-1]
            opLast = self._orderPacks[lastOrderId]
            lastSl = opLast.info["lastSl"]
            for orderId in list(orderSet):
                op = self._orderPacks[orderId]
                # 通过改一张单绑定的AutoExitInfo属性修改止损止盈
                if self.isAutoExit(op):
                    ae = op.info[AutoExitInfo.TYPE]
                    if op.order.direction == constant.DIRECTION_LONG:
                        self.setAutoExit(op, lastSl)
                        self.globalStatus['longStopLoss'] = lastSl
                        modify = 1
                    elif op.order.direction == constant.DIRECTION_SHORT:
                        self.setAutoExit(op, lastSl)
                        self.globalStatus['shortStopLoss'] = lastSl
                        modify = 1
        return modify

    def moveStopLoss(self, bar, orderSet):
        if len(self.orderAllList)>0:
            lastOrderId = self.orderAllList[-1]
            opLast = self._orderPacks[lastOrderId]
            ae = opLast.info[AutoExitInfo.TYPE]
            slGap = opLast.order.price_avg*self.trailingPct

            for orderId in list(orderSet):
                op = self._orderPacks[orderId]
                # 通过改一张单绑定的AutoExitInfo属性修改止损止盈
                if self.isAutoExit(op):
                    if op.order.direction == constant.DIRECTION_LONG:
                        if (bar.high - ae.stoploss) >= 2 * slGap:
                            self.setAutoExit(op, (ae.stoploss+slGap)*1.001)
                            self.globalStatus['longTrailingStopLoss'] = (ae.stoploss+slGap)*1.001
                    elif op.order.direction == constant.DIRECTION_SHORT:
                        if (ae.stoploss - bar.low) >= 2 * slGap:
                            self.setAutoExit(op, (ae.stoploss - slGap)*0.999)
                            self.globalStatus['shortTrailingStopLoss'] = (ae.stoploss-slGap)*0.999

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
            self.moveStopLoss(bar, idSet)

    def onBar(self, bar):
        # 必须继承父类方法
        super().onBar(bar)
        # on bar下触发回测洗价逻辑
        engineType = self.getEngineType()  # 判断engine模式
        if engineType == 'backtesting':
            # 定时控制，开始
            self.checkOnPeriodStart(bar)
            # 回测时的下单手数按此方法调整
            self.lot1 = int(200000 / bar.close)
            self.lot2 = int(200000 / bar.close)
        # 定时清除已出场的单
            self.checkOnPeriodStart(bar)
            self.checkOnPeriodEnd(bar)

            for idSet in self.orderDict.values():
                self.delOrderID(idSet)
                modify = self.modifyStopLoss(bar, idSet)
                if not modify:
                    self.moveStopLoss(bar, idSet)

        # 执行策略逻辑
        self.strategy(bar)

    def on5MinBar(self, bar):
        engineType = self.getEngineType()  # 判断engine模式
        if engineType != 'backtesting':
            self.writeCtaLog('globalStatus%s'%(self.globalStatus))
            self.notifyPosition('longVolume', self.getHoldVolume((self.orderDict['orderFirstLongSet']|self.orderDict['orderSecondLongSet'])), 'ChannelPos')
            self.notifyPosition('shortVolume', self.getHoldVolume((self.orderDict['orderFirstShortSet']|self.orderDict['orderSecondShortSet'])), 'ChannelPos')

    def strategy(self, bar):
        envPeriod= self.timeframeMap["envPeriod"]
        filterPeriod= self.timeframeMap["filterPeriod"]
        signalPeriod= self.timeframeMap["signalPeriod"]
        addPosPeriod = self.timeframeMap["addPosPeriod"]
                
        # 根据出场信号出场
        exitSig = self.exitSignal(envPeriod, filterPeriod, signalPeriod)
        self.exitOrder(exitSig)

        # 根据进场信号进场
        entrySig = self.entrySignal(envPeriod, filterPeriod, signalPeriod)
        self.entryOrder(entrySig, bar)

        # 根据信号加仓
        addPosSig = self.addPosSignal(addPosPeriod)
        self.addPosOrder(bar, addPosSig)

    def isStopControled(self):
        return self.currentTime < self.lastOrderDict['nextExecuteTime']

    def exitSignal(self, envPeriod, filterPeriod, signalPeriod):
        exitSignal = 0
        arrayPrepared1, amEnv = self.arrayPrepared(envPeriod)
        arrayPrepared2, amFilter = self.arrayPrepared(filterPeriod)
        arrayPrepared3, amSingal = self.arrayPrepared(signalPeriod)

        algorithm = adxDiTmaSignal()
        if arrayPrepared1 and arrayPrepared2 and arrayPrepared3:
            adxCanTrade, adxTrend, adxMa = algorithm.adxEnv(amEnv, self.paraDict)
            filterCanTrade = algorithm.fliterVol(amFilter, self.paraDict)
            maExit, sma, lma, envMa = algorithm.tmaExitSignal(amSingal, self.paraDict)

            if maExit==-1:
                exitSignal = 'exitLong'
            elif maExit==1:
                exitSignal = 'exitShort'
            if filterCanTrade==-1:
                exitSignal = 'closeAll'
        return exitSignal

    def exitOrder(self, exitSignal):
        # if exitSignal=='exitAll':
        #     for orderID in (self.orderDict['orderFirstLongSet']|self.orderDict['orderFirstShortSet']|self.orderDict['orderSecondLongSet']|self.orderDict['orderSecondShortSet']):
        #         op = self._orderPacks[orderID]
        #         self.composoryClose(op)
        if exitSignal=='exitLong':
            for orderID in (self.orderDict['orderFirstLongSet']|self.orderDict['orderSecondLongSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)
        elif exitSignal=='exitShort':
            for orderID in (self.orderDict['orderFirstShortSet']|self.orderDict['orderSecondShortSet']):
                op = self._orderPacks[orderID]
                self.composoryClose(op)

    def entrySignal(self, envPeriod, filterPeriod, signalPeriod):
        arrayPrepared1, amEnv = self.arrayPrepared(envPeriod)
        arrayPrepared2, amFilter = self.arrayPrepared(filterPeriod)
        arrayPrepared3, amSignal = self.arrayPrepared(signalPeriod)
        arrayPrepared = arrayPrepared1 and arrayPrepared2 and arrayPrepared3
        if arrayPrepared:
            algorithm = adxDiTmaSignal()
            adxCanTrade, adxTrend, adxMa = algorithm.adxEnv(amEnv, self.paraDict)
            filterCanTrade = algorithm.fliterVol(amFilter, self.paraDict)
            maDirection, sma, lma, envMa = algorithm.tmaEntrySignal(amSignal, self.paraDict)
            
            self.globalStatus['adxCanTrade'] = adxCanTrade
            self.globalStatus['filterCanTrade'] = filterCanTrade
            self.globalStatus['maDirection'] = maDirection
            self.globalStatus['adxTrend'] = adxTrend[-1]
            self.globalStatus['adxMa'] = adxMa[-1]
            self.globalStatus['sma'] = sma[-3:]
            self.globalStatus['lma'] = lma[-3:]
            self.globalStatus['envMa'] = envMa[-3:]
            
            entrySignal = 0
            if (adxCanTrade == 1) and (filterCanTrade == 1):
                if (maDirection == 1) and not self.isStopControled():
                    entrySignal = 1
                elif (maDirection == -1) and not self.isStopControled():
                    entrySignal = -1
        return entrySignal

    def entryOrder(self, entrySignal, bar):
        # 避免onTrade没走完就走加仓的方法设置的开关
        buyExecute, shortExecute = self.priceExecute(bar)
        engineType = self.getEngineType()
        if entrySignal ==1 and not self.isStopControled():
            if not (self.orderDict['orderFirstLongSet'] or self.orderDict['orderSecondLongSet']):
                for orderID2 in self.timeLimitOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, self.lot2, 120).vtOrderIDs:                
                    self.orderDict['orderSecondLongSet'].add(orderID2)
                    op2 = self._orderPacks[orderID2]
                    self.setAutoExit(op2, (bar.close*(1-self.trailingPct)), (bar.close*(1+self.takeProfitSecondPct)))
                # 分批下单
                longPos = self.lot1//self.orderTime
                stepOrder = self.makeStepOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, self.lot1, longPos, self.totalSecond, self.stepSecond)
                orderID1 = stepOrder.parentID
                op1 = self._orderPacks[orderID1]
                # 设置止损
                self.setAutoExit(op1, (bar.close*(1-self.trailingPct)), (bar.close*(1+self.takeProfitFirstPct)))
                op1.info["lastSl"] = (bar.close*(1-self.trailingPct))                
                self.orderDict['orderFirstLongSet'].add(orderID1)
                self.orderAllList.append(orderID1)

        elif entrySignal ==-1 and not self.isStopControled():
            if not (self.orderDict['orderFirstShortSet'] or self.orderDict['orderSecondShortSet']):
                for orderID2 in self.timeLimitOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, self.lot2, 120).vtOrderIDs:
                    self.orderDict['orderSecondShortSet'].add(orderID2)
                    op2 = self._orderPacks[orderID2]
                    self.setAutoExit(op2, (bar.close*(1+self.trailingPct)), (bar.close*(1-self.takeProfitSecondPct)))
                # 分批下单                
                shortPos = self.lot1//self.orderTime
                stepOrder = self.makeStepOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, self.lot1, shortPos, self.totalSecond, self.stepSecond)
                orderID1 = stepOrder.parentID
                op1 = self._orderPacks[orderID1]
                # 设置止损
                self.setAutoExit(op1, (bar.close*(1+self.trailingPct)), (bar.close*(1-self.takeProfitFirstPct)))
                op1.info["lastSl"] = (bar.close*(1+self.trailingPct))
                self.orderDict['orderFirstShortSet'].add(orderID1)
                self.orderAllList.append(orderID1)

    # 计算可加仓的信号
    def addPosSignal(self, addPosPeriod):
        erCanAddPos = 1
        # arrayPrepared, amAddPos = self.arrayPrepared(addPosPeriod)
        # if arrayPrepared:
        #     algorithm = adxDiTmaSignal()
        #     erCanAddPos, erSma, erLma = algorithm.erAdd(amAddPos, self.paraDict)
        return erCanAddPos

    # 通过上一张单来设置止损止盈
    def addPosOrder(self, bar, addPosSignal):
        buyExecute, shortExecute = self.priceExecute(bar)
        if not (self.orderDict['orderFirstLongSet'] or self.orderDict['orderFirstShortSet']):
            self.nPos = 0
            self.orderAllList = []
        else:
            lastOrderID = self.orderAllList[-1]
            op = self._orderPacks[lastOrderID]
            if self.isAutoExit(op):
                ae = op.info[AutoExitInfo.TYPE]
                lastOrder = op.order.price_avg
                algorithm = adxDiTmaSignal()
                if addPosSignal and lastOrder:
                    if op.order.direction == constant.DIRECTION_LONG and (self.nPos < self.posTime):
                        # if ((bar.close/lastOrder - 1) >= self.addPct) and ((bar.close/lastOrder - 1)<=2*self.addPct):
                        if (lastOrder/bar.close - 1) >= self.addPct:
                            self.nPos += 1
                            addPosLot = int(algorithm.addLotList(self.paraDict)[self.nPos-1]*self.lot1)
                            longAddPos = addPosLot//self.orderTime
                            self.globalStatus['longAddPos'] = (self.nPos, longAddPos)
                            stepAddOrder = self.makeStepOrder(ctaBase.CTAORDER_BUY, bar.vtSymbol, buyExecute, addPosLot, longAddPos, self.totalSecond, self.stepSecond)
                            addOrderID = stepAddOrder.parentID
                            opAdd = self._orderPacks[addOrderID]
                            self.setAutoExit(opAdd, (bar.close*(1-self.trailingPct)), ae.takeprofit)
                            opAdd.info["lastSl"] = (bar.close*(1-self.trailingPct))
                            self.orderDict['orderFirstLongSet'].add(addOrderID) 
                            self.orderAllList.append(addOrderID)
                    elif op.order.direction == constant.DIRECTION_SHORT and (self.nPos < self.posTime):
                        # if ((lastOrder/bar.close - 1) >= self.addPct) and ((lastOrder/bar.close - 1) <= 2*self.addPct):
                        if (bar.close/lastOrder - 1) >= self.addPct:
                            self.nPos += 1
                            addPosLot = int(algorithm.addLotList(self.paraDict)[self.nPos-1]*self.lot1)
                            shortAddPos = addPosLot//self.orderTime
                            self.globalStatus['shortAddPos'] = (self.nPos, shortAddPos)
                            stepAddOrder = self.makeStepOrder(ctaBase.CTAORDER_SHORT, bar.vtSymbol, shortExecute, addPosLot, shortAddPos, self.totalSecond, self.stepSecond)
                            addOrderID = stepAddOrder.parentID
                            opAdd = self._orderPacks[addOrderID]
                            self.setAutoExit(opAdd, (bar.close*(1+self.trailingPct)), ae.takeprofit)
                            opAdd.info["lastSl"] = (bar.close*(1+self.trailingPct))
                            self.orderDict['orderFirstShortSet'].add(addOrderID) 
                            self.orderAllList.append(addOrderID)

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        super().onOrder(order)
        pass
    # ----------------------------------------------------------------------
    # 成交后用成交价设置第一张止损止盈
    def onTrade(self, trade):
        super().onTrade(trade)
        pass

    def onStopOrder(self, so):
        """停止单推送"""
        pass