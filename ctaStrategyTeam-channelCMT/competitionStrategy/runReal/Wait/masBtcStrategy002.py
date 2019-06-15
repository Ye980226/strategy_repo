from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta
import pandas as pd
import numpy as np
from datetime import timedelta, datetime
import time

class Mas_Strategy(CtaTemplate):
    className = 'Mas_Strategy'
    author = 'Sky'
    # 策略交易标的

    # 策略参数
    Window1 = 20 ; Window2 = 40 ; Window3 = 60 ; Window4 = 90
    barPeriod=150
    lot = 1
    prop = 1.4; prop1 = 0.6;prop2 = 0.9; trailingPercent = 4
    stopRatio = 0.02 ; profitMultiplier = 5
    holdHour = 25;expectReturn = 0.001;stopControlTime = 6
    # 策略变量
    transactionPrice = {}  # 记录成交价格
    intraTradeHighDict = {}
    intraTradeLowDict = {}
    firstpos = {} ; nPos = {} ; openTime = {}; closeTime = {}
    trend = {};wave = {};cross = {}
    longStop = {};longexit = {};shortStop = {};shortexit = {};Ma_exit = {}
    n = 0

    # 自维护仓位与订单
    ownPosDict = {};orderDict = {}
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'Window1',
                 'Window2',
                 'Window3',
                 'Window4',
                 'trailingPercent',
                 'lot',
                 'prop',
                 'prop1',
                 'stopRatio',
                 'profitMultiplier']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict',
               'trend',
               'wave',
               'cross',
               'n']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict',

                ]

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""

        super().__init__(ctaEngine, setting)

        # ----------------------------------------------------------------------

    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略%s：初始化' % self.className)

        self.setArrayManagerSize(self.barPeriod)
        self.tickObject = {s: None for s in self.symbolList}
        self.trend = {s: 0 for s in self.symbolList}
        self.wave = {s: 0 for s in self.symbolList}
        self.cross = {s: 0 for s in self.symbolList}
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.Ma_exit = {s: 0 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 0 for s in self.symbolList}

        self.firstpos = {s: 0 for s in self.symbolList}
        self.longStop = {s: 0 for s in self.symbolList}
        self.longexit = {s: 0 for s in self.symbolList}
        self.shortStop = {s: 0 for s in self.symbolList}
        self.shortexit = {s: 0 for s in self.symbolList}

        # riskControlVar
        self.closeTime = {s: None for s in self.symbolList}
        self.openTime = {s: None for s in self.symbolList}
        self.stopLossControl = {s: 0 for s in self.symbolList}

        self.mail("sky__MA_Strategy initial！！Goodluck to me~~")
        # posManage
        nPos = {s: 0 for s in self.symbolList}
        for s in self.symbolList:
            self.ownPosDict = {s + '_LONG': 0, s + '_SHORT': 0}
            self.orderDict = {s + '_OPEN': [], s + '_CLOSE': []}
        self.toExcuteOrders = {}
        self.toExcuteOrdersID = 0
        self.putEvent()
        '''
        在点击初始化策略时触发,载入历史数据,会推送到onbar去执行updatebar,但此时ctaEngine下单逻辑为False,不会触发下单.
        '''

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略%s：启动' % self.className)
        # self.ctaEngine.loadSyncData(self)    # 加载当前正确的持仓
        self.putEvent()
        '''
        在点击启动策略时触发,此时的ctaEngine会将下单逻辑改为True,此时开始推送到onbar的数据会触发下单.
        '''

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略%s：停止' % self.className)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onRestore(self):
        """从错误状态恢复策略（必须由用户集成实现）"""
        #         self.writeCtaLog(u'策略%s：恢复策略状态成功' % self.Name)
        self.putEvent()


    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        if not self.dataBlock(dataTime=tick.datetime, now=datetime.now(), maxDelay=5):
            engineType = self.getEngineType()
            if engineType == 'trading':
                symbol = tick.vtSymbol
                self.tickObject[symbol] = tick
            else:
                pass

    # 过滤掉实盘推数据可能产生的阻塞(5s延迟)
    def dataBlock(self, dataTime, now, maxDelay=5):
        if abs(now - dataTime).total_seconds() > maxDelay:
            self.writeCtaLog(
                "数据推送阻塞,跳过该次推送:now=%s,dataTime=%s" % (now.strftime("%Y-%m-%d %H:%M:%S"),
                                                      dataTime.strftime("%Y-%m-%d %H:%M:%S")))
            return True
        else:
            return False

    # orderManagement--------------------------------------------------------

    def timeSleep(self):
        engineType=self.getEngineType()
        if engineType == 'trading':
            time.sleep(3)
        else:
            return

    def cancelCloseOrder(self, bar):
        symbol = bar.vtSymbol
        haveCloseOrder = len(self.orderDict[symbol + '_CLOSE'])
        if haveCloseOrder:
            for closeOrderId in list(self.orderDict[symbol + '_CLOSE']):
                self.cancelOrder(closeOrderId)
            self.timeSleep()
        else:
            return

    def cancelOpenOrder(self, bar):
        symbol = bar.vtSymbol
        haveOpenOrder = len(self.orderDict[symbol + '_OPEN'])
        if haveOpenOrder:
            for openOrderId in list(self.orderDict[symbol + '_OPEN']):
                self.cancelOrder(openOrderId)
            self.timeSleep()
        else:
            return

    def priceExecute(self, bar):
        symbol = bar.vtSymbol
        engineType = self.getEngineType()
        if engineType == 'trading':
            buyExecute = self.tickObject[symbol].upperLimit*0.99
            shortExecute = self.tickObject[symbol].lowerLimit*1.01
        else:
            buyExecute = bar.close * 1.02
            shortExecute = bar.close * 0.98
        return buyExecute, shortExecute

    def buyCheckExtend(self, bar, volume=None):
        symbol = bar.vtSymbol
        if not volume:
            volume = self.lot
        buyExecute, shortExecute = self.priceExecute(bar)
        self.cancelOpenOrder(bar)
        buyOpenOrderList = self.buy(symbol, buyExecute, volume)
        self.orderDict[symbol + '_OPEN'].extend(buyOpenOrderList)

    def shortCheckExtend(self, bar, volume=None):
        symbol = bar.vtSymbol
        if not volume:
            volume = self.lot
        buyExecute, shortExecute = self.priceExecute(bar)
        self.cancelOpenOrder(bar)
        shortOpenOrderList = self.short(symbol, shortExecute, volume)
        self.orderDict[symbol + '_OPEN'].extend(shortOpenOrderList)

    def coverCheckExtend(self, bar):
        symbol = bar.vtSymbol
        buyExecute, shortExecute = self.priceExecute(bar)
        self.cancelCloseOrder(bar)
        coverCloseOrderList = self.cover(symbol, buyExecute, self.ownPosDict[symbol + "_SHORT"])
        self.orderDict[symbol + '_CLOSE'].extend(coverCloseOrderList)

    def sellCheckExtend(self, bar):
        symbol = bar.vtSymbol
        buyExecute, shortExecute = self.priceExecute(bar)
        self.cancelCloseOrder(bar)
        sellCloseOrderList = self.sell(symbol, shortExecute, self.ownPosDict[symbol + '_LONG'])
        self.orderDict[symbol + '_CLOSE'].extend(sellCloseOrderList)

    def sellTakeProfitOrder(self, trade, price, volume):
        symbol = trade.vtSymbol
        sellCloseOrderList = self.sell(symbol, price, volume)
        self.orderDict[symbol + '_CLOSE'].extend(sellCloseOrderList)

    def coverTakeProfitOrder(self, trade, price, volume):
        symbol = trade.vtSymbol
        coverCloseOrderList = self.cover(symbol, price, volume)
        self.orderDict[symbol + '_CLOSE'].extend(coverCloseOrderList)

    # ----------------------------------------------------------------------
    def on5sBar(self, bar):
        self.writeCtaLog('###5s###posDict:%s###' % (self.ownPosDict))
#     def onBar(self, bar):
        symbol = bar.vtSymbol
        # 持有多头仓位
        self.onBarStopLoss(bar)
        self.onBarExecute(bar)
        self.onBarPosition(bar)

        self.putEvent()

        # ----------------------------------------------------------------------

    def onBarPosition(self, bar):
        symbol = bar.vtSymbol
        if (self.ownPosDict[symbol + '_LONG'] > 0):
            if self.n<3:
                if (bar.close/self.transactionPrice[symbol]-1)>=0.02:
                    self.buyCheckExtend(bar,volume=self.lot*2)
                    self.n+=1

        elif (self.ownPosDict[symbol + '_SHORT'] > 0):
            if self.n<3:
                if (bar.close/self.transactionPrice[symbol]-1)<=-0.02:
                    self.shortCheckExtend(bar,volume = self.lot*2)
                    self.n+=1

#     def checkHoldTime(self, bar):
#         symbol = bar.vtSymbol
#         if self.openTime[symbol]:
#             longUnexpect = (bar.close / self.transactionPrice[symbol] - 1) < self.expectReturn
#             shortUnexpect = (self.transactionPrice[symbol] / bar.close - 1) < self.expectReturn
#             if ((bar.datetime - self.openTime[symbol]) >= timedelta(hours=self.holdHour)):
#                 if (self.ownPosDict[symbol + "_LONG"] > 0) and longUnexpect:
#                     self.sellCheckExtend(bar)
#                     self.writeCtaLog('longUnexpect_Sell')
#                     self.openTime[symbol] = None
#                 elif (self.ownPosDict[symbol + "_SHORT"] > 0) and shortUnexpect:
#                     self.coverCheckExtend(bar)
#                     self.writeCtaLog('shortUnexpect_Cover')
#                     self.openTime[symbol] = None


    def onBarStopLoss(self, bar):
        symbol = bar.vtSymbol
        if self.closeTime[symbol]:
            if (bar.datetime - self.closeTime[symbol]) >= timedelta(hours=self.stopControlTime):
                self.stopLossControl[symbol] = 0

        if self.ownPosDict[symbol + '_LONG'] == 0 and self.ownPosDict[symbol + "_SHORT"] == 0:
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999
            self.flag = 1
        # 计算止损止盈价位
        elif (self.ownPosDict[symbol + '_LONG'] > 0):
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.longStop[symbol] = self.intraTradeHighDict[symbol] * (1 - self.trailingPercent / 100)
            if bar.close <= self.Ma_exit[symbol]:
                self.sellCheckExtend(bar)
                self.n =0

        #self.writeCtaLog('买入价格%s,多头触发出场价格:%s,止损价格:%s'%(self.transactionPrice[symbol],bar.close,self.Ma_exit[symbol]))
        elif (self.ownPosDict[symbol + '_SHORT'] > 0):
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.shortStop[symbol] = self.intraTradeLowDict[symbol] * (1 + self.trailingPercent / 100)
            #self.writeCtaLog('firstpos%s,shortexit:%s,shortStop:%s' % (self.firstpos[symbol],self.shortexit, self.shortStop))
            if bar.close >= self.shortStop[symbol]:
                self.coverCheckExtend(bar)
                self.n = 0
                #self.writeCtaLog('卖出价格%s,空头触发出场价格:%s,止损价格:%s' % (self.firstpos[symbol],bar.close,self.shortStop))


    def onBarExecute(self, bar):
        symbol = bar.vtSymbol

        if (self.cross[symbol] == 1 and self.trend[symbol] == 1 and self.wave[symbol] == 1)\
        and (self.ownPosDict[symbol +  "_LONG"] == 0):
            # 如果金叉时手头没有持仓，则直接做多
            if self.stopLossControl[symbol] == -1:
                self.stopLossControl[symbol] = 0
            if self.stopLossControl[symbol] == 0:
                if (self.ownPosDict[symbol +  "_SHORT"] == 0):
                    self.buyCheckExtend(bar)
                    self.writeCtaLog('%sdiscover a long signal,time:%s,bar.close:%s,cross:%s,trend:%s,wave:%s' % (
                        symbol, bar.datetime,bar.close,self.cross[symbol], self.trend[symbol], self.wave[symbol]))
                # 如果有空头持仓，则先平空，再做多
                elif self.ownPosDict[symbol +  "_SHORT"] != 0:
                    self.coverCheckExtend(bar)
                    self.buyCheckExtend(bar)

        # 死叉和金叉相反
        elif (self.cross[symbol] == -1 and self.trend[symbol] == 1 and self.wave[symbol] == -1)\
        and (self.ownPosDict[symbol +  "_SHORT"] == 0):
            if self.stopLossControl[symbol] == 1:
                self.stopLossControl[symbol] = 0
            if self.stopLossControl[symbol] == 0:
                if (self.ownPosDict[symbol +  "_LONG"] == 0):
                    self.shortCheckExtend(bar)
                    # self.writeCtaLog('%sdiscover a short signal,time:%s,bar.close:%s,cross:%s,trend:%s,wave:%s' % (
                    #     symbol, bar.datetime, bar.close, self.cross[symbol], self.trend[symbol], self.wave[symbol]))
                elif self.ownPosDict[symbol +  "_LONG"] != 0:
                    self.sellCheckExtend(bar)
                    self.shortCheckExtend(bar)
        #self.writeCtaLog('%son30minbar,time:%s,close:%s,cross:%s,trend:%s,wave:%s,n:%s'%(symbol,bar.datetime,bar.close,self.cross[symbol],self.trend[symbol],self.wave[symbol],self.n))
        self.putEvent()


    def on30MinBar(self, bar):
        """60分钟K线推送"""
        symbol = bar.vtSymbol

        am30 = self.getArrayManager(symbol, "30m")
        if not am30.inited:
            return

        Ma1 = ta.MA(am30.close, self.Window1)

        Ma2 = ta.MA(am30.close, self.Window2)

        Ma3 = ta.MA(am30.close, self.Window3)

        Ma4 = ta.MA(am30.close, self.Window4)

        maxma = max(Ma1[-1], Ma2[-1], Ma3[-1], Ma4[-1])
        minma = min(Ma1[-1], Ma2[-1], Ma3[-1], Ma4[-1])

        self.Ma_exit[symbol] = minma

        agg = (maxma - minma) / minma * 100
        if agg < self.prop:
            self.trend[symbol] = 1
        else:
            self.trend[symbol] = 0

        change = (am30.close[-1] - am30.close[-2]) / am30.close[-2] * 100
        if change > self.prop1 and change < self.prop2:
            self.wave[symbol] = 1
        elif change <= self.prop1:
            self.wave[symbol] = -1
        else:
            self.wave[symbol] = 0

        # 判断买卖
        if Ma1[-1] > Ma1[-2] and am30.close[-1] > Ma1[-1]:
            self.cross[symbol] = 1
        elif Ma1[-1] < Ma1[-2] and am30.close[-1] < Ma1[-1]:
            self.cross[symbol] = -1
        else:
            self.cross[symbol] = 0

    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        symbol = order.vtSymbol
        if order.status == STATUS_UNKNOWN:
            self.mail(u'出现未知订单，需要策略师外部干预,ID:%s, symbol:%s,direction:%s,offset:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))


        elif order.status == STATUS_REJECTED:
            self.mail(u'Rejected,ID:%s, symbol:%s,direction:%s,offset:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))

        if order.thisTradedVolume != 0:
            # dealamount 不等于 0 表示有订单成交
            content = u'成交信息播报,ID:%s, symbol:%s, directionL%s, offset:%s, price:%s'%\
                      (order.vtOrderID, order.vtSymbol, order.direction, order.offset, order.price)
            self.mail(content)

        if order.status in STATUS_FINISHED:
            if order.offset == OFFSET_OPEN:
                self.orderDict[symbol + '_OPEN'].remove(str(order.vtOrderID))
            elif order.offset == OFFSET_CLOSE:
                self.orderDict[symbol + '_CLOSE'].remove(str(order.vtOrderID))
        self.putEvent()




    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交信息变化推送"""
        symbol = trade.vtSymbol
        self.writeCtaLog('tradeTime:%s,offset:%s,transactionPrice:%s ,ownPosDict%s' \
                         % (trade.tradeDatetime, trade.offset, self.transactionPrice, self.ownPosDict))
        self.writeCtaLog('Quarter####Mas_Strategy:%s' % (symbol))

        if trade.offset == OFFSET_OPEN:
            self.transactionPrice[symbol] = trade.price
            self.openTime[symbol] = trade.tradeDatetime
            self.closeTime[symbol] = None
            if self.flag == 1:
                self.firstpos[symbol] = trade.price
                self.flag = 0
        elif trade.offset == OFFSET_CLOSE:
            self.openTime[symbol] = None
            self.closeTime[symbol] = trade.tradeDatetime

        # ownPosDict
        if trade.direction == DIRECTION_LONG and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_LONG'] += int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_LONG'] -= int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_SHORT'] += int(trade.volume)
        elif trade.direction == DIRECTION_LONG and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_SHORT'] -= int(trade.volume)

        if trade.direction == DIRECTION_SHORT:
            self.stopLossControl[symbol] = 1
        elif trade.direction == DIRECTION_LONG:
            self.stopLossControl[symbol] = -1

        self.longexit[symbol] = self.firstpos[symbol] * (1 + self.profitMultiplier * self.stopRatio)
        self.shortexit[symbol] = self.firstpos[symbol] * (1 - self.profitMultiplier * self.stopRatio)

        if trade.offset == OFFSET_OPEN:
            if trade.direction == DIRECTION_LONG:
                self.sellTakeProfitOrder(trade,self.longexit[symbol],trade.volume)
                self.writeCtaLog('long### tp1:%s' %self.longexit[symbol])

            elif trade.direction == DIRECTION_SHORT:
                self.coverTakeProfitOrder(trade,self.shortexit[symbol],trade.volume)
                self.writeCtaLog('short### tp1:%s' %self.shortexit[symbol])
#         print(trade.tradeDatetime, self.ownPosDict)
    # ---------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass