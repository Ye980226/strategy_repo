import numpy as np
import talib as ta
from datetime import timedelta, datetime
import time
from vnpy.trader.utils.templates.orderTemplate import *
from diverence import DiverGenceGet as dg


'''
使用移动止损的办法控制出场
2019年2月15日 10:25:29
每当价格按照理想的方向移动self.addPercent，对应的止损也移动self.addPercent

2019年2月19日 15:54:11
过滤掉最近有极端行情的bar
'''

########################################################################
class Strategy_signalDI(OrderTemplate):
    
    className = 'Strategy_signalDI'
    author = 'unknown author'

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']
    # 参数列表，保存了参数的名称
    paramList = [
        'symbolList',
        'posSize',
        'miniTick',
        'addTick',
         
        ########## macd信号指标参数 ###########
        'diPeriod',  # 在多少分钟的分钟bar下计算macd
        'fastPeriod', # 10
        'slowPeriod', # 100
        'DIshield',

        ########### 过滤条件参数 ############
        'ADXPeriod', # 在多少分钟的分钟bar下计算ADX
        'ADXpara',
        'ADXshield_up',  # adx不能小于这个值
        'ADXshield_down', #adx不能大于这个值
        'atrPeriod',
        'atrShield',

        ########### 风控参数 #############
        'addPercent',
        'stopLoss',
        'maxPos',
        'timeStopLoss', #  时间止损 单位min
        'signalWait',  # signalWait长时间内出现的同方向信号过滤掉mi
        
        ### 时间周期
        'timeframeMap'
        ]
    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
        print(setting) 
        self.writeCtaLog(str(setting))
        self.symbol = setting['symbolList'][0]

        ### 从setting中读取adx参数
        self.adxPara = {
            'ADXpara':setting['ADXpara'],
            'ADXshield_up':setting['ADXshield_up'],
            'ADXshield_down':setting['ADXshield_down']
        }

        ### 从setting中读取DI参数
        self.DIpara = {
            'fastPeriod':setting['fastPeriod'],
            'slowPeriod':setting['slowPeriod'],
            'DIshield':setting['DIshield'],
            'DImaPeriod':1
        }
        
        ### 内部存贮订单并管理的字典
        self.orderDict = {}
        self.lastKlineTime = {
            i:None for i in self.timeframeMap
        }

        ### 和指标相关的全局变量
        self.Filter = False

        ### 平仓后过滤掉接下来一段时间的信号
        self.buyClose = datetime(2000,1,1)
        self.shortClose = datetime(2000,1,1)

        ###### 储存其它数据用于画图分析 #####
        self.dilog = {
            'datetime':[],
            'dima':[],
            'di_line2':[],
            'di':[],
        }
        self.atr = {
            'datetime':[],
            'atr':[]
        }
        self.doubleMa = {
            'datetime':[],
            'mafast':[],
            'maslow':[]
        }
    
    # ----------------------------------------------------------------------
    def perpare_date(self):
        """
        注册bar事件，不需要特别推送，但需要获得对应的k线
        """
        for timeframe in self.timeframeMap:
            self.registerOnBar(self.symbol,timeframe,None)
    
    # --------------------------------------------------------------------
    def barPrepared(self, period):
        """
        判断是否产生了个新bar——有新bar则进行信号计算
        """
        am = self.getArrayManager(self.symbol, period)
        if not am.inited:
            self.writeCtaLog("am is not inited:%s" % (period,))
            return False, None
        if self.lastKlineTime[period] is None or am.datetime[-1] > self.lastKlineTime[period]:
            return True, am
        else:
            return False, None

    # --------------------------------------------------------------------
    def updateLastKlineTime(self):
        """更新K线时间"""
        for period in self.timeframeMap:
            self.lastKlineTime[period] = self.getArrayManager(self.symbol, period).datetime[-1]

    
    # ----------------------------------------------------------------------
    def signalWaitCheck(self,opDict,datetime,signalWait):
        """
        用于过滤相邻时间不超过signalWait的同方向信号
        """
        buy, short = True, True
        if len(opDict) == 0:
            pass
        else:
            for vtOrderID in opDict:
                op = self._orderPacks.get(vtOrderID, None)
                if op:
                    if op.order.direction == DIRECTION_LONG and (datetime-op.order.orderDatetime).total_seconds()/60 < signalWait:
                        buy = False
                    elif op.order.direction == DIRECTION_SHORT and (datetime-op.order.orderDatetime).total_seconds()/60 < signalWait:
                        short = False 
        return buy, short 
    
    # -------------------------------------------------------------------
    def possitionCheck(self,opDict, buyMax=1, shortMax=1):
        """
        用于控制最大持仓数量
        """
        buy ,short = True, True
        buyNum, shortNum = 0, 0
        if len(opDict) == 0:
            pass
        else:
            for vtOrderID in opDict:
                op = self._orderPacks.get(vtOrderID, None)
                if op:
                    if op.order.direction == DIRECTION_LONG:
                        buyNum += op.order.tradedVolume
                    else:
                        shortNum += op.order.tradedVolume
            if buyNum+1 >= buyMax:
                buy = False            
            if shortNum+1 >= shortMax:
                short = False
        return buy, short    

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.writeCtaLog(u'策略初始化')
        self.setArrayManagerSize(1000)
        self.perpare_date()
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略启动')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略停止')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        super().onTick(tick)
        pass
    
    # ---------------------------------------------------------------------
    def on10sBar(self,bar):
        """
        实盘中在10秒bar里面洗价
        """
        self.checkOnPeriodStart(bar)
        #--------------------------------------------
        self.moveStopLoss(bar,self.addPercent)
        # -------------------------------------------
        self.checkOnPeriodEnd(bar)

    # ------------------------------------------------------------------------
    def delOrderID(self,bar):
        """
        从self.OrderDict中删除已经完成的订单
        """
        for vtOrderID in list(self.orderDict):
            op = self._orderPacks[vtOrderID]
            if self.orderClosed(op):
                if op.order.direction == DIRECTION_LONG:
                    self.buyClose = bar.datetime
                else:
                    self.shortClose = bar.datetime
                del self.orderDict[vtOrderID]

    # ------------------------------------------------------------------------
    def moveStopLoss(self,bar,addPercent):
        """
        用于判断移动止损，移动方法如下：
        以多头为例，当观测到最近一个bar的最高价相比起成交价已经高出addPercent倍以close作为止损价格
        """
        pass
#         for vtOrderID in list(self.orderDict):
#             op = self._orderPacks.get(vtOrderID, None)
#             if not op:
#                 continue 
#             price = op.info['addMessage']['price']
#             exitPrice = op.info['addMessage']['exitPrice']
#             if op.order.direction == DIRECTION_LONG:
#                 if (bar.high-price)/price > addPercent:  ### 这个判断用于防止止损比addPercent大时意外移动的情况
#                     if bar.close-addPercent*price > exitPrice:
#                         self.writeCtaLog('多头持仓止损发生移动，从%s移动到%s'%(exitPrice, bar.close))
#                         self.setAutoExit(op,stoploss=bar.close)
#                         self.setConditionalClose(op,self.timeStopLoss*60,None)  ### 移动止损后重新计算时间止损
#             else:
#                 if (bar.low-price)/price < -addPercent:
#                     if bar.close+addPercent*price < exitPrice:
#                         self.writeCtaLog('空头持仓止损发生移动，从%s移动到%s'%(exitPrice, bar.close))
#                         self.setAutoExit(op,stoploss=bar.close)
#                         self.setConditionalClose(op,self.timeStopLoss*60,None) 
    # ----------------------------------------------------------------------
    def getPos(self):
        buypos, shortpos = 0, 0
        for vtOrderID in self.orderDict:
            op = self._orderPacks[vtOrderID]
            openVolume = op.order.tradedVolume
            closeVolume = self.orderClosedVolume(op)
            if op.order.direction == DIRECTION_LONG:
                buypos += openVolume-closeVolume
            else:
                shortpos += openVolume-closeVolume
        return buypos, shortpos

    # --------------------------------------------------------------------
    def onBar(self,bar):
        super().onBar(bar)
        #### 执行策略逻辑
        self.strategy(bar)
        self.delOrderID(bar) 
        self.moveStopLoss(bar,self.addPercent)
        buypos, shortpos = self.getPos()
        self.writeCtaLog('每分钟打印仓位, 多头持仓:%s, 空头持仓:%s'%(buypos,shortpos))
        if self.getEngineType() == 'backtesting':
            self.checkOnPeriodStart(bar)
            self.checkOnPeriodEnd(bar)
              
    # ---------------------------------------------------------------------
    def strategy(self,bar):
        """
        策略逻辑主体，设置指标计算，信号组装，环境判断和下单
        """
        #### 根据出场信号出场
        exitSignal = self.exitSignal(bar)
        self.exitOrder(exitSignal,bar)
        entrySignal = self.entrySignal(bar)
        self.entryOrder(entrySignal,bar)
        self.updateLastKlineTime()
        

    # --------------------------------------------------------------------
    def exitSignal(self,bar):
        """平仓信号"""
        return False

    # ---------------------------------------------------------------------
    def exitOrder(self,exitSignal,bar):
        """"平仓"""
        pass

    # ----------------------------------------------------------------------
    def entrySignal(self,bar):
        """计算发单信号"""
        
        Signal = 0
        
        ### 按照filterPeriod获得信号
        TF, amfilter = self.barPrepared(self.ADXPeriod)
        if TF:
            Filter, _ = dg.ADXget(self,amfilter,self.adxPara)        
            self.Filter = Filter
        else:
            Filter = self.Filter
        
        ### di指标获得的信号
        TF, amSignal = self.barPrepared(self.diPeriod)
        if TF:
            atr = ta.ATR(amSignal.high,amSignal.low,amSignal.close,self.atrPeriod)[-1]
            if atr<self.atrShield:
                self.DIpara['DImaPeriod'] = 10
                self.DIpara['DIshield'] = 40
            else:
                self.DIpara['DImaPeriod'] = 1
                self.DIpara['DIshield'] = 10
            Signal, DI, _ = dg.DIget(self,amSignal, self.DIpara)
    
            ### 根据DI来确定交易方向
            dima = ta.EMA(DI,10)

            if dima[-1] > -self.DIshield:
                Signal = 0  

            fastMa = ta.EMA(amSignal.close, self.fastPeriod)
            slowMa = ta.EMA(amSignal.close, self.slowPeriod)

            self.doubleMa['datetime'].append(bar.datetime)
            self.doubleMa['mafast'].append(fastMa[-1])
            self.doubleMa['maslow'].append(slowMa[-1])

            self.dilog['datetime'].append(bar.datetime)
            self.dilog['di'].append(DI[-1])
            self.dilog['di_line2'].append(-10)
            self.dilog['dima'].append(dima[-1])
            self.atr['datetime'].append(bar.datetime)
            self.atr['atr'].append(atr)

        ### 按照当前持仓判断是否允许进场
        buy1, short1 = self.possitionCheck(self.orderDict,self.maxPos,self.maxPos)
        ### 按照上一个信号时间判断是否要过滤掉本次信号
        # buy2, short2 = self.signalWaitCheck(self.orderDict,bar.datetime,self.signalWait)

        ### 综合信号下单
        if Signal==1 and buy1 and self.Filter \
        and (bar.datetime-self.buyClose).total_seconds()/60 > 60:
            self.writeCtaLog('策略判断出现多信号，买入开仓')
        elif Signal==-1 and short1 and self.Filter \
        and (bar.datetime-self.shortClose).total_seconds()/60 > 60:
            self.writeCtaLog('策略判断出现空信号，卖出开仓')
        else:
            Signal = 0
        
        return Signal

    # ---------------------------------------------------------------------
    def entryOrder(self,signal,bar):
        """
        得到信号后判断能否下单
        """
        if self.getEngineType() == 'trading':
            volume = self.posSize
        else:
            volume = self.posSize/bar.close
        
        ### 根据信号下单 ###
        if signal == -1:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_SHORT,bar.vtSymbol,
            bar.close-self.addTick*self.miniTick,volume, 120)
            for vtOrderID in tlo.vtOrderIDs:
                op = self._orderPacks[vtOrderID]
                ### 向info中添加addMessage帮助后续便捷操作
                op.info['addMessage'] = {'openTime':bar.datetime,'type':'short','move':0,
                'price':bar.close,'exitPrice':bar.close*(1+self.stopLoss)}
                self.orderDict[vtOrderID] = True
                self.setConditionalClose(op,self.timeStopLoss*60,None)
        
        elif signal == 1:
            tlo = self.timeLimitOrder(ctaBase.CTAORDER_BUY,bar.vtSymbol,
            bar.close+self.addTick*self.miniTick,volume,120)
            for vtOrderID in tlo.vtOrderIDs:
                op = self._orderPacks[vtOrderID]
                ### 向info中添加addMessage帮助后续便捷操作
                op.info['addMessage'] = {'openTime':bar.datetime,'type':'buy','move':0,
                'price':bar.close,'exitPrice':bar.close*(1-self.stopLoss)}
                self.orderDict[vtOrderID] = True
                self.setConditionalClose(op,self.timeStopLoss*60,None)

    # ----------------------------------------------------------------------
    def onOrder(self,order):
        super().onOrder(order)
        self.writeCtaLog(f'onOrderLog,orderID:{order.vtSymbol}{order.vtOrderID}{order.status}{order.totalVolume}')
        # print(f'onOrderLog,orderID:{order.vtSymbol}{order.vtOrderID}{order.status}{order.totalVolume}')

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        super().onTrade(trade)
        self.writeCtaLog('发生了成交，方向：%s, 开平:%s, 成交价:%s'%(trade.direction, trade.offset, trade.price))
        # self.mail('发生了成交，方向：%s, 开平:%s, 成交价:%s, 已成交量:%s'%(trade.direction, trade.offset, trade.price,trade.volume))
        # print('%s,%s发生了成交，方向：%s, 开平:%s, 成交价:%s'%(trade.tradeTime,trade.vtOrderID,trade.direction, trade.offset, trade.price))
        
        ### 获得成交价
        if trade.vtOrderID in self.orderDict:
            op = self._orderPacks.get(trade.vtOrderID, None)
            if op:
                ### 绑定止盈和止损 
                if trade.direction == DIRECTION_LONG:
                    op.info['price'] = trade.price
                    op.info['exitPrice'] = (1-self.stopLoss)*trade.price
                    self.setAutoExit(op,stoploss=(1-self.stopLoss)*trade.price,takeprofit=(1+self.addPercent)*trade.price)
#                     self.setAutoExit(op,stoploss=(1-self.stopLoss)*trade.price)
                    self.writeCtaLog('多头开仓, 止损价:%s'%((1-self.stopLoss)*trade.price))
                elif trade.direction == DIRECTION_SHORT:
                    op.info['price'] = trade.price
                    op.info['exitPrice'] = (1+self.stopLoss)*trade.price
                    self.setAutoExit(op,stoploss=(1+self.stopLoss)*trade.price,takeprofit=(1-self.addPercent)*trade.price)
#                     self.setAutoExit(op,stoploss=(1+self.stopLoss)*trade.price)
                    self.writeCtaLog('空头开仓，止损价为%s'%((1+self.stopLoss)*trade.price))