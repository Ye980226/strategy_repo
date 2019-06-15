# encoding: UTF-8
# moreSignal

"""
盘口策略
观测到指标出现挂单
挂单超过10s立即撤单
成交后挂出止盈单，同时每个tick检查是否到达止损位置
发生一次止损之后一段时间内不进场
持仓超过1分钟的单全部平掉

需要传入的参数：

用于计算是否入场的指标（使用给定指标计算挂单方向和挂单价格）

挂单未成交时间长度: openTime
持仓最长时间: holdTime
止盈价格绝对值: takeProfit
止损价格绝对值: stopLoss

2018年11月14日 23:15:13  
新增发生一次止损后30分钟内同方向不再进场

2018年11月15日 10:06:17
新增对到期单的处理，记录原有的stopLoss价格，同时按照盘口挂限价单
经过self.timeAdd时间若未成交循环操作，直至全部成交/超过self.maxTimeAdd次数后按照市价出场

2018年11月15日 15:42:34
修改‘新增发生一次止损后30分钟内同方向不再进场’为‘新增发生x次止损后30分钟内同方向不再进场’

2018年11月16日 10:28:41
需要一个判断大波动结束了的指标，使用均线粘合

2018年11月27日 14:26:18
新增对unknown和reject订单的处理

2018年11月29日 16:45:09
修改入场条件
当前volumeChange=0的tick相比上一个满足：
askPrice1_{t} > askPrice_{t-1}*(1+minTick) and askPrice1_{t} < askPrice_{t-1}*(1-maxTick)
sum(askVolumek_{t-1}) where askPricek_{t-1} < askPrice1_{t} 在当前价格上方挂卖单
反之挂买单

2018年12月1日 16:01:45
增加日志输出，aim Price 和 tick.datetime
简单修改应对 tick 堵塞问题， V3不需要再判断tick堵塞问题

2018年12月5日 17:49:09
修改止盈和止损按照对手价判断。
考虑将撤单逻辑写入tick逻辑中

2018年12月6日 10:43:03
为适配V3接口，修改撤单逻辑为收到未成交以后才开始撤单
"""

from vnpy.trader.vtConstant import *
# EMPTY_STRING, DIRECTION_LONG, DIRECTION_SHORT,OFFSET_OPEN, OFFSET_CLOSE,
# STATUS_CANCELLED,STATUS_NOTTRADED,STATUS_PARTTRADED,STATUS_ALLTRADED
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)
from vnpy.trader.app.ctaStrategy.ctaBase import *                                                   
from collections import defaultdict
import numpy as np
import pandas as pd
import talib as ta
import time
from datetime import datetime, timedelta
########################################################################
class ImpluseV1Strategy(CtaTemplate):
    """配对交易策略"""
    className = 'ImpluseV1Strategy'
    author = 'HFgroup'

    # 策略交易标的
    #symbolList = []                 # 初始化为空
    symbol = EMPTY_STRING

    # 策略变量
    posSize = 1
    waitCount = 0
    ### 记录表现 ####
    #### 从左往右分别是 止损出场次数，到期出场次数，止盈出场次数 ####
    longWin = [0,0,0]
    shortWin = [0,0,0]
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'longWin',
                 'shortWin']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(ImpluseV1Strategy, self).__init__(ctaEngine, setting)
        self.posSize = setting['posSize']
        # 固定比率止盈和固定比率止损
        self.takeProfitRatio = setting['takeProfitRatio']
        self.stopLossRatio = setting['stopLossRatio']
        # 挂单位置Ratio
        self.mom_move = setting['mom_move']
        self.maxnumber = setting['maxnumber']
        # 挂单和持仓时间(s)
        self.openTime = setting['openTime']
        self.holdTime = setting['holdTime']

    
    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' % self.name)
        
        # 读取交易品种  
        self.symbol = self.symbolList[0]   
        self.hfamDict = {sym: ArrayManager(200) for sym in self.symbolList}

        ####################### 挂撤单逻辑需要用到的参数等 ######
        # 挂撤单需要用到的各种字典
        self.sellOrderDict, self.coverOrderDict = {}, {}
        self.buyOrderDict, self.shortOrderDict = {},{}
        # 控制可以挂出的最大单量
        self.Longcount, self.Shortcount = 0, 0
        # 记录挂单总数和仓位
        self.Longcount , self.Shortcount = 0 ,0 
        # 到期出场挂单时间
        # self.timeAdd:持仓时间超过1分钟后按盘口价格出场的挂单等待时间， maxTimeAdd，最多重复挂几次
        self.timeAdd , self.maxTimeAdd = 5,2
        # 出现x次止损后同方向过滤掉接下来一段时间的信号
        self.buyLossMax, self.shortLossMax = 2, 2
        # 记录各仓位连续止损的次数
        self.buyLossNum, self.shortLossNum = 0, 0
        self.waitTo = False
        # 生成1分钟bar推送
        self.generateBarDict(self.onBar,size=100)
        # 生成1s高频bar，不用于updateBar，仅用于1s一次触发逻辑
        self.generateHFBar(1)
        self.lastTickTime = datetime.now()
        self.tickTimeList = []
        self.tickLastVolume = []
        self.tickLastPrice = []
        self.sign = [[0,0],'both']


        engine = self.getEngineType()
        # 回测读取数据
        if engine == 'trading':
            ### 实盘从交易所读取数据
            kline = self.loadHistoryBar(self.symbol, '1min', 100)
            ### 将读取的数据填入amDict
            for bar in kline:
                self.amDict[self.symbol].updateBar(bar)
        else:
            self.initBacktesingData()

        self.putEvent()
    
    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' % self.name) 
        # date = str(datetime.now()) 
        # self.file = open(date+'tickData.txt','a')  
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' % self.name)
        # self.file.close()
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        
        # #######################
        # self.file.write(str(tick.__dict__) + ' \n')
        # avsum = tick.askVolume1+tick.askVolume2+tick.askVolume3
        # bvsum = tick.bidVolume1+tick.bidVolume2+tick.bidVolume3
        # self.file.write(u'datetime:%s,vc:%s,askPrice1:%s,askPrice3:%s,bidPrice1:%s,bidPrice3:%s,lastPrice:%s,lastVolume:%s,avsum:%s, bvsum:%s \n'
        # %(tick.datetime,tick.volumeChange,tick.askPrice1,tick.askPrice3,tick.bidPrice1,tick.bidPrice3,tick.lastPrice,tick.lastVolume,avsum,bvsum))
        # #######################

        ### 生成对应的bar并推送 
        self.hfDict[tick.vtSymbol].updateHFBar(tick) 
        self.bgDict[tick.vtSymbol].updateTick(tick)
        self.ThisTick = tick
        

        ############# 防止tick拥堵以保证当前tick是最新的tick ##############
        if abs(tick.localTime-datetime.now()).total_seconds()>0.5:
            return

        ################ 计算信号逻辑 ###########################
        if tick.volumeChange != 0:
            
            ############# 记录过去1分钟volumeChange=1的lastVolume成一个list
            self.tickTimeList.append(tick.datetime)
            self.tickLastVolume.append(tick.lastVolume)
            self.tickLastPrice.append(tick.lastPrice)
            return

        if tick.datetime.second != self.lastTickTime.second:
            self.lastTickTime = tick.datetime
            buy, short = True, True
            shortPrice, shortVolume = tick.askPrice1*(1+self.mom_move),self.posSize
            buyPrice, buyVolume = tick.bidPrice1*(1-self.mom_move),self.posSize
        else:
            buy, short = False, False
            return
        
        ############# 根据过去1分钟的成交情况判断是否需要下单 ###############
        Near = np.array(self.tickTimeList) > tick.datetime - timedelta(seconds=60)
        a =  len(np.array(self.tickLastVolume)[Near])
        b = np.sum(np.array(self.tickLastVolume)[Near])
        self.sign[0] = {'长度':a,'数量':b}

        ################# 根据信号下单逻辑 #######################
        if self.Longcount + self.Shortcount < self.maxnumber: 
            if short and (self.sign[1]=='shortOnly' or self.sign[1]=='both'):
                self.writeCtaLog('sign:%s'%self.sign)    
                orderID = self.short(self.symbol,shortPrice,shortVolume)[0]
                self.shortOrderDict[orderID] = {'time':tick.datetime,'takeProfit':shortPrice*(1-self.takeProfitRatio),
                'sendOrderTime':tick.datetime,
                'stopLoss':shortPrice*(1+self.stopLossRatio),'aimPrice':shortPrice,'type':False,'sign':self.sign}
                self.writeCtaLog(u'short卖开ID:%s, askPrice1:%s, datetime:%s'%(orderID,tick.askPrice1,tick.datetime))
                self.Shortcount+=shortVolume  
                    
            if buy and (self.sign[1]=='buyOnly' or self.sign[1]=='both'):
                self.writeCtaLog('sign:%s'%self.sign)
                orderID = self.buy(self.symbol,buyPrice,buyVolume)[0]
                self.buyOrderDict[orderID] = {'time':tick.datetime,'takeProfit':buyPrice*(1+self.takeProfitRatio),
                'sendOrderTime':tick.datetime,
                'stopLoss':buyPrice*(1-self.stopLossRatio),'aimPrice':buyPrice,'type':False,'sign':self.sign}
                self.writeCtaLog(u'buy买开ID:%s, bidPrice1:%s, datetime:%s'%(orderID,tick.bidPrice1,tick.datetime))
                self.Longcount+=buyVolume  
              
        self.putEvent()

    # ----------------------------------------------------------------------
    def onHFBar(self,bar):
        """收到高频（秒级）bar推送""" 
        # print('HFFFFFF',bar.datetime,len(self.ThisTickList))
        self.hfamDict[self.symbol].updateBar(bar)
        ####### 信号发出器：计算并判断是否挂单，输出挂单价格和指标 #######
        
        """
        buy = True, buyPrice = 买入价格, buyVolume = 买入手数, takeProfit:止盈价格，stopLoss:止损价格
        short = True, shortPrice = 卖出价格, shortVolume = 卖出手数，takeProfit:止盈价格，stopLoss:止损价格
        
        订单管理逻辑如下：
        当收到一个买信号，策略会首先判断当前仓位+未成交订单是否已到最大仓位，如果是，
        拒绝这次信号，否则按照信号挂出订单，同时记录订单号，发单时间，固定止盈价格和固定止损价格

        之后每隔HFBar策略会检查这张单的情况，对于未成交的订单，超过一段时间会撤销
        对于已成交的订单，策略会检查是否到达止损条件
        
        卖出信号类似
        """
        ################# 撤单逻辑 ######################
        ###### 再同一个事件中，撤单逻辑要在发单前 #########
        # for orderID in self.buyOrderDict:
        #     if (self.ThisTick.datetime-self.buyOrderDict[orderID]['time']).total_seconds(): #and self.buyOrderDict[orderID]['type']:
        #         self.cancelOrder(orderID)
        #         self.writeCtaLog(u'到达最大等待时间，撤销未成交订单:%s, 当前时间:%s'%(orderID,bar.datetime))
        #         self.buyOrderDict[orderID]['time'] += timedelta(seconds=50)
        # for orderID in self.shortOrderDict:
        #     if (self.ThisTick.datetime-self.shortOrderDict[orderID]['time']).total_seconds(): #and self.shortOrderDict[orderID]['type']:
        #         self.cancelOrder(orderID)
        #         self.writeCtaLog(u'到达最大等待时间, 撤销未成交订单:%s, 当前时间:%s'%(orderID,bar.datetime))
        #         self.shortOrderDict[orderID]['time'] += timedelta(seconds=50)

        # 过去1分钟振幅达到2%不进场：
        buySign = (self.hfamDict[self.symbol].close[-1]-min(self.hfamDict[self.symbol].low[-60:]))/(self.hfamDict[self.symbol].close[-60]+0.0001)
        shortSign = (max(self.hfamDict[self.symbol].high[-60:])-self.hfamDict[self.symbol].close[-60])/(self.hfamDict[self.symbol].close[-60]+0.0001)

        if buySign > 0.02 and shortSign < 0.02:
            self.sign[1] = 'buyOnly' 
            self.writeCtaLog('change sign 1 to buyOnly, price:%s'%self.ThisTick.lastPrice)
            # 平掉已经开的空仓
            # for orderID in self.coverOrderDict:
            #     if self.coverOrderDict[orderID]['type'] != 'stopLoss':
            #         self.coverOrderDict[orderID]['type'] = 'stopLoss'
            #         self.writeCtaLog(u'Oh no,信号判断空头危险,止损价:%s,当前价格:%s,aimPrice:%s,sendOrderTime:%s,sign:%s,收益:%s'%(self.coverOrderDict[orderID]['stopLoss'],price,
            #                         self.coverOrderDict[orderID]['aimPrice'],self.coverOrderDict[orderID]['sendOrderTime'],self.coverOrderDict[orderID]['sign'],
            #                         (price-self.coverOrderDict[orderID]['aimPrice'])/self.coverOrderDict[orderID]['aimPrice']))
            #         self.cancelOrder(orderID)                
        elif buySign < 0.02 and shortSign > 0.02:
            self.sign[1] = 'shortOnly' 
            self.writeCtaLog('change sign 1 to shortOnly, price:%s'%self.ThisTick.lastPrice)
            # 平掉已经开的多仓
            # for orderID in self.sellOrderDict:
            #     if self.sellOrderDict['type'] != 'stopLoss':
            #         self.sellOrderDict[orderID]['type'] = 'stopLoss'
            #         self.writeCtaLog(u'Oh no,信号判断的多头危险,止损价:%s,当前价格:%s,aimPrice:%s,sendOrderTime:%s,sign:%s'%(self.sellOrderDict[orderID]['stopLoss'],price,
            #                         self.sellOrderDict[orderID]['aimPrice'],self.sellOrderDict[orderID]['sendOrderTime'],self.sellOrderDict[orderID]['sign']))
            #         self.cancelOrder(orderID)
        elif buySign > 0.02 and shortSign > 0.02:
            self.writeCtaLog('change sign 1 to Stop, price:%s'%self.ThisTick.lastPrice)
            self.sign[1] = 'Stop'
        else:
            self.sign[1] = 'both'  
        
        ################# 固定止损和时间止损逻辑 ####################      
        for orderID in self.sellOrderDict:

            price = self.ThisTick.bidPrice1      #平多头使用 bidPrice1 判断止损
            
            if price < self.sellOrderDict[orderID]['stopLoss'] and self.sellOrderDict[orderID]['type']!='stopLoss' :
                self.writeCtaLog(u'Oh no,多头止损触发,止损价:%s,当前价格:%s,aimPrice:%s,sendOrderTime:%s,sign:%s,收益：%s'%(self.sellOrderDict[orderID]['stopLoss'],price,
                                self.sellOrderDict[orderID]['aimPrice'],self.sellOrderDict[orderID]['sendOrderTime'],self.sellOrderDict[orderID]['sign'],
                                (price-self.sellOrderDict[orderID]['aimPrice'])/(self.sellOrderDict[orderID]['aimPrice']+0.0001)))
                self.sellOrderDict[orderID]['type'] = 'stopLoss'
                self.cancelOrder(orderID)
            
            elif (bar.datetime-self.sellOrderDict[orderID]['time']).total_seconds() > self.sellOrderDict[orderID]['hold']:
                self.writeCtaLog(u'Oh 多头时间止损触发,止损价:%s,当前价格:%s,aimPrice:%s,sendOrderTime:%s,sign:%s,收益：%s'%(self.sellOrderDict[orderID]['stopLoss'],price,
                                self.sellOrderDict[orderID]['aimPrice'],self.sellOrderDict[orderID]['sendOrderTime'],self.sellOrderDict[orderID]['sign'],
                                (price-self.sellOrderDict[orderID]['aimPrice'])/(self.sellOrderDict[orderID]['aimPrice']+0.0001)))
                self.sellOrderDict[orderID]['type'] = 'timeout'
                self.cancelOrder(orderID)
                self.sellOrderDict[orderID]['time'] += timedelta(seconds=50)
        
        for orderID in self.coverOrderDict:

            price = self.ThisTick.askPrice1  #平空头使用 askPrice1 判断止损
            
            if price > self.coverOrderDict[orderID]['stopLoss'] and self.coverOrderDict[orderID]['type']!='stopLoss':
                self.writeCtaLog(u'Oh no,空头止损触发,止损价:%s,当前价格:%s,aimPrice:%s,sendOrderTime:%s,sign:%s,收益:%s'%(self.coverOrderDict[orderID]['stopLoss'],price,
                                self.coverOrderDict[orderID]['aimPrice'],self.coverOrderDict[orderID]['sendOrderTime'],self.coverOrderDict[orderID]['sign'],
                                (price-self.coverOrderDict[orderID]['aimPrice'])/(self.coverOrderDict[orderID]['aimPrice']+0.0001)))
                self.coverOrderDict[orderID]['type'] = 'stopLoss'
                self.cancelOrder(orderID)
            
            elif (bar.datetime-self.coverOrderDict[orderID]['time']).total_seconds() > self.coverOrderDict[orderID]['hold']:
                self.writeCtaLog(u'Oh 空头时间止损触发,止损价:%s,当前价格:%s,aimPrice:%s,sendOrderTime:%s,sign:%s,收益:%s'%(self.coverOrderDict[orderID]['stopLoss'],price,
                                self.coverOrderDict[orderID]['aimPrice'],self.coverOrderDict[orderID]['sendOrderTime'],self.coverOrderDict[orderID]['sign'],
                                (price-self.coverOrderDict[orderID]['aimPrice'])/(self.coverOrderDict[orderID]['aimPrice']+0.0001)))
                self.coverOrderDict[orderID]['type'] = 'timeout'
                self.cancelOrder(orderID)
                self.coverOrderDict[orderID]['time'] += timedelta(seconds=50)
        
        self.putEvent()
    
    # ----------------------------------------------------------------------
    def onBar(self,bar):


        Near = np.sum(np.array(self.tickTimeList) < datetime.now()-timedelta(seconds = 120))
        self.tickTimeList = self.tickTimeList[Near:]
        self.tickLastVolume = self.tickLastVolume[Near:]
        self.writeCtaLog(u'当前长度 :%s'%len(self.tickTimeList))         
        pass


    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""   
        self.writeCtaLog(u'收到订单状态：%s, :status:%s, traded:%s, total:%s,order.price:%s'%(order.vtOrderID,order.status,order.tradedVolume,order.totalVolume,order.price)) 

        if order.status == STATUS_NOTTRADED:
            ######## 收到未成交回报才开始进入撤单逻辑 #########
            if order.vtOrderID in self.buyOrderDict:
                self.cancelOrder(order.vtOrderID)
            elif order.vtOrderID in self.shortOrderDict:
                self.cancelOrder(order.vtOrderID)                

        #### 对成交单，止损单和止盈单进行操作
        elif order.status == STATUS_PARTTRADED:
            price = order.price
            volume = order.thisTradedVolume
            # 回测中没有order.thisTradedVolume，需要修改
            # volume = 1
            time = datetime.now()
            ##### 现在order.orderTime是一个空值     
            ### 开仓单成交了要立刻补上对应价格平仓单
            if order.vtOrderID in self.buyOrderDict:
                orderID = self.sell(self.symbol,self.buyOrderDict[order.vtOrderID]['takeProfit'],volume)[0]
                self.sellOrderDict[orderID] = {'time':time,'price':price,'type':None,'hold':self.holdTime,'timestop':0,'TimeOut':1,
                                            'sendOrderTime':self.buyOrderDict[order.vtOrderID]['sendOrderTime'],'aimPrice':self.buyOrderDict[order.vtOrderID]['aimPrice'],
                                            'sign':self.buyOrderDict[order.vtOrderID]['sign'],
                                            'stopLoss':self.buyOrderDict[order.vtOrderID]['stopLoss'],'total':volume}
                
            elif order.vtOrderID in self.shortOrderDict:
                orderID = self.cover(self.symbol,self.shortOrderDict[order.vtOrderID]['takeProfit'],volume)[0]
                self.coverOrderDict[orderID] = {'time':time,'price':price,'type':None,'hold':self.holdTime,'timestop':0,'TimeOut':1,
                                            'sendOrderTime':self.shortOrderDict[order.vtOrderID]['sendOrderTime'],'aimPrice':self.shortOrderDict[order.vtOrderID]['aimPrice'],
                                            'sign':self.shortOrderDict[order.vtOrderID]['sign'],
                                            'stopLoss':self.shortOrderDict[order.vtOrderID]['stopLoss'],'total':volume}

        
        elif order.status == STATUS_ALLTRADED:
            price = order.price
            volume = order.thisTradedVolume
            # 回测中没有order.thisTradedVolume，需要修改
            # volume = 1
            time = datetime.now()
            ### 开仓单成交了要立刻补上对应价格平仓单
            if order.vtOrderID in self.buyOrderDict:
                orderID = self.sell(self.symbol,self.buyOrderDict[order.vtOrderID]['takeProfit'],volume)[0]
                self.sellOrderDict[orderID] = {'time':time,'price':price,'type':None,'hold':self.holdTime,'timestop':0,'TimeOut':1,
                                            'sendOrderTime':self.buyOrderDict[order.vtOrderID]['sendOrderTime'],'aimPrice':self.buyOrderDict[order.vtOrderID]['aimPrice'],
                                            'sign':self.buyOrderDict[order.vtOrderID]['sign'],
                                            'stopLoss':self.buyOrderDict[order.vtOrderID]['stopLoss'],'total':volume}
                ### 全部成交的订单要从字典里删除
                del self.buyOrderDict[order.vtOrderID]
            elif order.vtOrderID in self.shortOrderDict:
                orderID = self.cover(self.symbol,self.shortOrderDict[order.vtOrderID]['takeProfit'],volume)[0]
                self.coverOrderDict[orderID] = {'time':time,'price':price,'type':None,'hold':self.holdTime,'timestop':0,'TimeOut':1,
                                            'sendOrderTime':self.shortOrderDict[order.vtOrderID]['sendOrderTime'],'aimPrice':self.shortOrderDict[order.vtOrderID]['aimPrice'],
                                            'sign':self.shortOrderDict[order.vtOrderID]['sign'],
                                            'stopLoss':self.shortOrderDict[order.vtOrderID]['stopLoss'],'total':volume}
                ### 全部成交的订单要从字典里删除
                del self.shortOrderDict[order.vtOrderID]
            ### 止盈单成交了要记录
            elif order.vtOrderID in self.sellOrderDict:
                self.Longcount -= order.totalVolume
                self.longWin[2] += self.sellOrderDict[order.vtOrderID]['TimeOut']
                ## 只有TimeOut为1的才是止盈单，timeOut为0是时间止损单
                if self.sellOrderDict[order.vtOrderID]['TimeOut'] > 0:
                    self.writeCtaLog(u'多头止盈出场_%s，Oh Yeah, aimPrice:%s, sendOrderTime:%s,sign:%s'%(order.vtOrderID,
                                    self.sellOrderDict[order.vtOrderID]['aimPrice'],self.sellOrderDict[order.vtOrderID]['sendOrderTime'],
                                    self.sellOrderDict[order.vtOrderID]['sign']))
                    self.buyLossNum = 0
                del self.sellOrderDict[order.vtOrderID]
            elif order.vtOrderID in self.coverOrderDict:
                self.Shortcount -= order.totalVolume
                self.shortWin[2] += self.coverOrderDict[order.vtOrderID]['TimeOut']
                ## 只有TimeOut为1的才是止盈单，timeOut为0是时间止损单
                if self.coverOrderDict[order.vtOrderID]['TimeOut'] > 0:
                     self.writeCtaLog(u'空头止盈出场_%s，Oh Yeah, aimPrice:%s,sendOrderTime:%s,sign:%s'%(order.vtOrderID,
                                    self.coverOrderDict[order.vtOrderID]['aimPrice'],self.coverOrderDict[order.vtOrderID]['sendOrderTime'],
                                    self.coverOrderDict[order.vtOrderID]['sign']))
                     self.shortLossNum = 0
                del self.coverOrderDict[order.vtOrderID]


        # 对已撤销单进行处理
        elif order.status == STATUS_CANCELLED:
            ## 撤销的是平仓单，进入价格止损或时间止损逻辑
            if order.vtOrderID in self.sellOrderDict:
                if self.sellOrderDict[order.vtOrderID]['type'] == 'stopLoss':
                    self.Longcount -= order.totalVolume - order.tradedVolume
                    self.sell(self.symbol,self.ThisTick.lowerLimit+0.005,order.totalVolume-order.tradedVolume)
                    self.longWin[0] += 1
                # elif self.sellOrderDict[order.vtOrderID]['type'] == 'timeout':
                else:
                    ## 对timeout的订单进行处理, 按照盘口价格挂单,是否使用对手价值得进一步考虑
                    self.longWin[1] += self.sellOrderDict[order.vtOrderID]['TimeOut']
                    if self.sellOrderDict[order.vtOrderID]['timestop'] < self.maxTimeAdd:
                        orderID  = self.sell(self.symbol,self.ThisTick.askPrice1-0.001,order.totalVolume-order.tradedVolume,priceType=PRICETYPE_MARKETPRICE)[0]
                        self.sellOrderDict[orderID] =  {'time':self.ThisTick.datetime,'price':self.ThisTick.askPrice1-0.001,'type':None,'hold':self.timeAdd,
                                                'aimPrice':0,'sign':self.sellOrderDict[order.vtOrderID]['sign'],
                                                'sendOrderTime':self.sellOrderDict[order.vtOrderID]['sendOrderTime'],                                                
                                                'timestop':self.sellOrderDict[order.vtOrderID]['timestop']+1,'TimeOut':0,
                                                'stopLoss':self.sellOrderDict[order.vtOrderID]['stopLoss'],'total':order.totalVolume-order.tradedVolume}
                    else:
                        ## 多次挂出均未成交的订单按照市价出场
                        self.sell(self.symbol,self.ThisTick.lowerLimit+0.001,order.totalVolume-order.tradedVolume)                     
                        self.Longcount -= order.totalVolume - order.tradedVolume
                ## 执行完全部操作后删除字典内原有的元素
                del self.sellOrderDict[order.vtOrderID]               
            
            elif order.vtOrderID in self.coverOrderDict:
                if self.coverOrderDict[order.vtOrderID]['type'] == 'stopLoss':
                    self.Shortcount -= order.totalVolume - order.tradedVolume
                    self.cover(self.symbol,self.ThisTick.upperLimit-0.005,order.totalVolume-order.tradedVolume)
                    self.shortWin[0] += 1
                else:
                    ## 对timeout的订单进行处理，按照盘口价格挂单,是否使用对手价值得进一步考虑
                    self.shortWin[1] += self.coverOrderDict[order.vtOrderID]['TimeOut']
                    if self.coverOrderDict[order.vtOrderID]['timestop'] < self.maxTimeAdd:
                        orderID = self.cover(self.symbol,self.ThisTick.bidPrice1+0.001,order.totalVolume-order.tradedVolume,priceType=PRICETYPE_MARKETPRICE)[0]  
                        self.coverOrderDict[orderID] = {'time':self.ThisTick.datetime,'price':self.ThisTick.bidPrice1+0.001,'type':None,'hold':self.timeAdd,
                                                'aimPrice':0,'sign':self.coverOrderDict[order.vtOrderID]['sign'],
                                                'sendOrderTime':self.coverOrderDict[order.vtOrderID]['sendOrderTime'],
                                                'timestop':self.coverOrderDict[order.vtOrderID]['timestop']+1,'TimeOut':0,
                                                'stopLoss':self.coverOrderDict[order.vtOrderID]['stopLoss'],'total':order.totalVolume-order.tradedVolume}    
                    else:
                        ## 多次挂出未成交的订单按照市价出场
                        self.cover(self.symbol,self.ThisTick.upperLimit-0.001,order.totalVolume-order.tradedVolume)
                        self.Shortcount -= order.totalVolume - order.tradedVolume
                ## 执行完全部操作后删除字典内原有的元素
                del self.coverOrderDict[order.vtOrderID]
            ## 撤销的是开仓单，删除字典并对可开数量进行修改
            elif order.vtOrderID in self.buyOrderDict:
                self.Longcount -= order.totalVolume-order.tradedVolume
                del self.buyOrderDict[order.vtOrderID]
            elif order.vtOrderID in self.shortOrderDict:
                self.Shortcount -= order.totalVolume - order.tradedVolume
                del self.shortOrderDict[order.vtOrderID]


        elif order.status == STATUS_UNKNOWN:
            ### 删除字典里保存的订单
            if order.vtOrderID in self.buyOrderDict:
                del self.buyOrderDict[order.vtOrderID]
            elif order.vtOrderID in self.shortOrderDict:
                del self.shortOrderDict[order.vtOrderID]
            else:
                self.writeCtaLog(u'平仓单出现unknown错误，订单编号:%s'%order.vtOrderID)

        ############# 发生平仓拒单重新进入发单逻辑 ##################
        elif order.status == STATUS_REJECTED:
            if order.vtOrderID in self.buyOrderDict:
                del self.buyOrderDict[order.vtOrderID]
            elif order.vtOrderID in self.shortOrderDict:
                del self.shortOrderDict[order.vtOrderID]
            elif '20018' in order.rejectedInfo:
                ###### 市价单被拒单重发
                self.writeCtaLog(u'20018市价单拒单重发，被拒订单：%s'%(order.vtOrderID))
                if order.direction == DIRECTION_LONG and order.offset == OFFSET_CLOSE:
                    self.cover(self.symbol,self.ThisTick.upperLimit-0.005,order.totalVolume)
                elif order.direction == DIRECTION_SHORT and order.offset == OFFSET_CLOSE:
                    self.sell(self.symbol,self.ThisTick.lowerLimit+0.005,order.totalVolume)
        
        self.putEvent()


    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        # 下单后报单  
        self.writeCtaLog(u'Long:%s,short:%s'%(self.longWin,self.shortWin))  
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass


