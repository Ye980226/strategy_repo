from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta
import pandas as pd
import numpy as np
from datetime import datetime,timedelta

class Mas_Strategy(CtaTemplate):
    className = 'Mas_Strategy'
    author = 'Sky'
    # 策略交易标的

    # 策略参数
    Window1 = 30 ; Window2 = 40 ; Window3 = 50 ; Window4 = 70
    barPeriod=150
    lot = 1
    prop = 0.5; prop1 = 0.4;prop2 = 0.7; trailingPercent = 3
    stopRatio = 0.02 ; profitMultiplier = 5
    stopControlTime = 6
    # 策略变量
    transactionPrice = {}  # 记录成交价格
    intraTradeHighDict = {}
    intraTradeLowDict = {}

    trend = 0;wave = 0;cross = 0

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
               'ownPosDict',
               'trend',
               'wave',
               'cross']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict']

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
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 0 for s in self.symbolList}
        self.longStop = 0
        self.shortStop = 99999
        # riskControlVar
        self.closeTime = None
        self.stopLossControl = 0
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
                self.tickObject = tick
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
    def cancelCloseOrder(self, bar):
        symbol = bar.vtSymbol
        haveCloseOrder = len(self.orderDict[symbol + '_CLOSE'])
        if haveCloseOrder:
            canceling = list(self.orderDict[symbol + '_CLOSE'])
            for closeOrderId in canceling:
                self.cancelOrder(closeOrderId)
            return False, canceling
        else:
            return True, []

    def priceExecute(self, bar):
        engineType = self.getEngineType()
        if engineType == 'trading':
            buyExecute = self.tickObject.upperLimit*0.99
            shortExecute = self.tickObject.lowerLimit*1.01
        else:
            buyExecute = bar.close * 1.02
            shortExecute = bar.close * 0.98
        return buyExecute, shortExecute

    def buyCheckExtend(self, bar, volume=None):
        symbol = bar.vtSymbol
        if not volume:
            volume = self.lot
        buyExecute, shortExecute = self.priceExecute(bar)
        if self.orderDict[symbol + '_OPEN']:
            self.writeCtaLog('haveOpenOrder_Pass')
        else:
            self.buyOpen(symbol, buyExecute, volume)
        

    def shortCheckExtend(self, bar, volume=None):
        symbol = bar.vtSymbol
        if not volume:
            volume = self.lot
        buyExecute, shortExecute = self.priceExecute(bar)
        if self.orderDict[symbol + '_OPEN']:
            self.writeCtaLog('haveOpenOrder_Pass')
        else:
            self.shortOpen(symbol, shortExecute, volume)
        

    def coverCheckExtend(self, bar):
        symbol = bar.vtSymbol
        buyExecute, shortExecute = self.priceExecute(bar)
        cancelled,canceling = self.cancelCloseOrder(bar)
        if cancelled:
            self.coverClose(symbol, buyExecute, self.ownPosDict[symbol + "_SHORT"])
        else:
            self.toExcuteOrdersID += 1
            self.toExcuteOrders[self.toExcuteOrdersID] = {
                "symbol": symbol,
                "price": buyExecute,
                "volume": self.ownPosDict[symbol + "_SHORT"],
                "orderType": "coverClose",
                "canceling":canceling
            }

    def sellCheckExtend(self, bar):
        symbol = bar.vtSymbol
        buyExecute, shortExecute = self.priceExecute(bar)
        cancelled,canceling = self.cancelCloseOrder(bar)
        if cancelled:
            self.sellClose(symbol, shortExecute, self.ownPosDict[symbol + '_LONG'])
        else:
            self.toExcuteOrdersID += 1
            self.toExcuteOrders[self.toExcuteOrdersID] = {
                "symbol": symbol,
                "price": shortExecute,
                "volume": self.ownPosDict[symbol + '_LONG'],
                "orderType": "sellClose",
                "canceling": canceling
            }

    def shortOpen(self, symbol, price, volume):
        
        shortOpenOrderList = self.short(symbol, price, volume)
        self.orderDict[symbol + '_OPEN'].extend(shortOpenOrderList)

    def buyOpen(self, symbol, price, volume):
      
        buyOpenOrderList = self.buy(symbol, price, volume)
        self.orderDict[symbol + '_OPEN'].extend(buyOpenOrderList)

    def sellClose(self,symbol, price, volume):
        sellCloseOrderList = self.sell(symbol, price, volume)
        self.orderDict[symbol + '_CLOSE'].extend(sellCloseOrderList)

    def coverClose(self,symbol, price, volume):
        coverCloseOrderList = self.cover(symbol, price, volume)
        self.orderDict[symbol + '_CLOSE'].extend(coverCloseOrderList)

    ##### orderManager ###############

    def onBar(self, bar):
        """收到1分钟K线推送"""
        symbol = bar.vtSymbol
        # 持有多头仓位
        self.onBarStopLoss(bar)
        self.onBarExecute(bar)    
        self.putEvent()

        # ----------------------------------------------------------------------

    def onBarStopLoss(self, bar):
        symbol = bar.vtSymbol
        if self.closeTime:
            if (bar.datetime - self.closeTime) >= timedelta(hours=self.stopControlTime):
                self.stopLossControl = 0

        if self.ownPosDict[symbol + '_LONG'] == 0 and self.ownPosDict[symbol + "_SHORT"] == 0:
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999

        # 计算止损止盈价位
        elif (self.ownPosDict[symbol + '_LONG'] > 0):
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.longStop = self.intraTradeHighDict[symbol] * (1 - self.trailingPercent / 100)
            if bar.close <= self.longStop:
                self.sellCheckExtend(bar)
            self.writeCtaLog('longStop:%s'%self.longStop)

        elif (self.ownPosDict[symbol + '_SHORT'] > 0):
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.shortStop = self.intraTradeLowDict[symbol] * (1 + self.trailingPercent / 100)
            
            if bar.close >= self.shortStop:
                self.coverCheckExtend(bar)
            self.writeCtaLog('shortStop:%s'%self.shortStop)
            
    def onBarExecute(self, bar):
        symbol = bar.vtSymbol

        if (self.cross == 1 and self.trend == 1 and self.wave == 1) and (self.ownPosDict[symbol +  "_LONG"] == 0):
        
            if self.stopLossControl == -1:
                self.stopLossControl = 0
            if self.stopLossControl == 0:
                if (self.ownPosDict[symbol +  "_SHORT"] == 0):
                    self.buyCheckExtend(bar)
     
                elif self.ownPosDict[symbol +  "_SHORT"] != 0:
                    self.coverCheckExtend(bar)
                    self.buyCheckExtend(bar,volume=self.lot)

        # 死叉和金叉相反
        elif (self.cross == -1 and self.trend == 1 and self.wave == -1) and (self.ownPosDict[symbol +  "_SHORT"] == 0):
            if self.stopLossControl == 1:
                self.stopLossControl = 0
            if self.stopLossControl == 0:
                if (self.ownPosDict[symbol +  "_LONG"] == 0):
                    self.shortCheckExtend(bar)
   
                elif self.ownPosDict[symbol +  "_LONG"] != 0:
                    self.sellCheckExtend(bar)
                    self.shortCheckExtend(bar)

        self.writeCtaLog('%son30minbar,time:%s,close:%s,cross:%s,trend:%s,wave:%s'%(symbol,bar.datetime,bar.close,self.cross,self.trend,self.wave))
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

        Ma5 = ta.KAMA(am30.close,20)

        maxma = max(Ma1[-1], Ma2[-1], Ma3[-1], Ma4[-1])
        minma = min(Ma1[-1], Ma2[-1], Ma3[-1], Ma4[-1])
        
        agg = (maxma - minma) / minma * 100
        if agg < self.prop:
            self.trend = 1
        else:
            self.trend = 0

        change = abs((am30.close[-1] - am30.close[-2]) / am30.close[-2] * 100)
        if change > self.prop1 and change < self.prop2 and am30.close[-1] > am30.open[-1]:
            self.wave = 1
        elif change > self.prop1 and change < self.prop2 and am30.close[-1] < am30.open[-1]:
            self.wave = -1
        else:
            self.wave = 0

        # 判断买卖
        if Ma1[-1] > Ma1[-2] and am30.close[-1] > Ma1[-1]:
            self.cross = 1
        elif Ma1[-1] < Ma1[-2] and am30.close[-1] < Ma1[-1]:
            self.cross = -1
        else:
            self.cross = 0

    def dealtoExcuteOrders(self, symbol):
        for ID in list(self.toExcuteOrders):
            order = self.toExcuteOrders[ID]
            if order["orderType"] in ["coverClose", "sellClose"]:
                # 前置要求中待撤销的订单已从orderDict中全部撤销
                if len(set(order["canceling"]) & set(self.orderDict[symbol + '_CLOSE'])) == 0:
                    if order["orderType"] == "coverClose":
                        self.coverClose(order["symbol"], order["price"], order["volume"])
                    elif order["orderType"] == "sellClose":
                        self.sellClose(order["symbol"], order["price"], order["volume"])
                    # 清除该待执行订单
                    del self.toExcuteOrders[ID]

    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        symbol = order.vtSymbol
        #print('order_vtSymbol:%s,type:%s'%(order.vtSymbol,type(order.vtSymbol)))
        if order.status == STATUS_UNKNOWN:
            self.mail(u'出现未知订单，需要策略师外部干预,ID:%s, symbol:%s,direction:%s,offset:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset))
        if order.status == STATUS_REJECTED:
            self.mail(u'Rejected,ID:%s, symbol:%s,direction:%s,offset:%s,拒单信息:%s'
                      % (order.vtOrderID, order.vtSymbol, order.direction, order.offset,order.rejectedInfo))
        if order.thisTradedVolume != 0:
            # dealamount 不等于 0 表示有订单成交
            content = u'成交信息播报,ID:%s, symbol:%s, directionL%s, offset:%s, price:%s'%\
                      (order.vtOrderID, order.vtSymbol, order.direction, order.offset, order.price)
            self.mail(content)

        if order.status in STATUS_FINISHED:
            if (order.offset == OFFSET_OPEN) and (str(order.vtOrderID) in self.orderDict[symbol + '_OPEN']):
                self.orderDict[symbol + '_OPEN'].remove(str(order.vtOrderID))
            elif (order.offset == OFFSET_CLOSE) and (str(order.vtOrderID) in self.orderDict[symbol + '_CLOSE']):
                self.orderDict[symbol + '_CLOSE'].remove(str(order.vtOrderID))
        # 触发撤单成功,扫描待执行订单的前置撤单要求是否达到，达到则触发对待执行订单的发单
        if order.status == STATUS_CANCELLED:
            self.dealtoExcuteOrders(symbol)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交信息变化推送"""
        symbol = trade.vtSymbol
        self.mail('tradeTime:%s,offset:%s,transactionPrice:%s ,ownPosDict%s' \
                         % (trade.tradeDatetime, trade.offset, self.transactionPrice[symbol], self.ownPosDict))
        self.writeCtaLog('Quarter####Mas_Strategy:%s' % (symbol))


        if trade.offset == OFFSET_OPEN:
            self.transactionPrice[symbol] = trade.price
            self.closeTime = None
        elif trade.offset == OFFSET_CLOSE:
            self.closeTime = trade.tradeDatetime
            if trade.direction == DIRECTION_SHORT:
                self.stopLossControl = 1
            elif trade.direction == DIRECTION_LONG:
                self.stopLossControl = -1

        # ownPosDict
        if trade.direction == DIRECTION_LONG and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_LONG'] += int(trade.volume)

        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_LONG'] -= int(trade.volume)
        elif trade.direction == DIRECTION_SHORT and trade.offset == OFFSET_OPEN:
            self.ownPosDict[symbol + '_SHORT'] += int(trade.volume)
            #print("self.ownPosDict[symbol + '_SHORT']:%s"%self.ownPosDict[symbol + '_SHORT'])
        elif trade.direction == DIRECTION_LONG and trade.offset == OFFSET_CLOSE:
            self.ownPosDict[symbol + '_SHORT'] -= int(trade.volume)
        

        self.longexit = self.transactionPrice[symbol] * (1 + self.profitMultiplier * self.stopRatio)
        self.shortexit = self.transactionPrice[symbol] * (1 - self.profitMultiplier * self.stopRatio)

        if trade.offset == OFFSET_OPEN:
            if trade.direction == DIRECTION_LONG:
                self.sellClose(trade.vtSymbol, self.longexit,self.ownPosDict[symbol + '_LONG'])
                self.writeCtaLog('longexit:%s' %self.longexit)
            elif trade.direction == DIRECTION_SHORT:
                self.coverClose(trade.vtSymbol, self.shortexit,self.ownPosDict[symbol + '_SHORT'])

                self.writeCtaLog('shortexit:%s' %self.shortexit)
    # ---------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass