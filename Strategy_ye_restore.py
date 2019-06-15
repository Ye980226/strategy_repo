# encoding: UTF-8

"""
简单配对交易策略模板
"""

from vnpy.trader.vtConstant import *

from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)

from collections import defaultdict
import time
import numpy as np
import talib as ta
import math
import os
import datetime
import json
########################################################################
class Strategy_Arbitrage_Restore(CtaTemplate):
    """配对交易策略"""
    className = 'FishingStrategy'
    author = 'zongzong'
    productType = 'FUTURE'
    # 策略交易标的
    symbolList = []                 # 初始化为空
    activeSymbol = EMPTY_STRING     # 主动品种
    passiveSymbol = EMPTY_STRING    # 被动品种
    asLongpos = EMPTY_STRING        # 主动品种多仓
    asShortpos = EMPTY_STRING       # 主动品种空仓
    psLongpos = EMPTY_STRING        # 被动品种多仓
    psShortpos = EMPTY_STRING       # 被动品种空仓
    posDict = {}                    # 仓位数据缓存
    eveningDict = {}                # 可平仓量数据缓存
    bondDict = {}                   # 保证金数据缓存
    

    # 策略变量
    posSize = 0
    miu=0
    alpha=0
    gap_base=0
    rev_floor=0
    pos=0
    volume=0
    # 用于记录上一个onTrade的结果，回测需要赋予初始状态，这里以全部空仓为初始
   

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'activeSymbol',
                 'passiveSymbol']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading','gap_base','miu','rev_floor','pos','volume']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict',
                'bondDict']


    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(Strategy_Arbitrage_Restore, self).__init__(ctaEngine, setting)
        
    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.activeSymbol=self.symbolList[0]#流动性好的品种
        self.passiveSymbol=self.symbolList[1]#流动性差的品种
        




        # 创建K线合成器对象
        self.bgDict = {
            sym: BarGenerator(self.onBar)
            for sym in self.symbolList
        }#用tick生成bar
        
        # 创建数组容器
        self.amDict = {
            sym: ArrayManager()
            for sym in self.symbolList
        }

        # 创建tick数据缓存容器
        self.tickBufferDict = {
            sym: []
            for sym in self.symbolList
        }#存下activeSymbol和passiveSymbol的tick
        self.barBufferDict={
            sym:[]
            for sym in self.symbolList
        }#存下activeSymbol和passiveSymbol的分钟bar

        self.spreadBuffer = []#存下midActivePrice-midPassivePrice
        

        self.midPassiveBuffer=[]#存下bid1和ask1的中间价
        self.midActiveBuffer=[]
        self.current_capital=500#留待之后做动态调仓
        
        self.active_passiveMap={}#把activeID和passiveID映射到一起
        # self.passive_infoMap={}#以passiveID为key,value分别是miu,gap,flag,pos,volume
        
        self.long_shortToInt={"多":-1,"空":1}#把多空跟pos参数映射起来
        self.pos_Map={-2:-1,2:0,-3:1}#在passiveSymbol被拒单时候调用
        self.passive_countList=[]
        self.close_openIdMap={}#平仓时的passiveID和开仓时的passiveID映射起来
        self.barSpreadBuffer=[]#bar.close的差值
        self.initbars=2000
        # self.writeCtaLog(u'%s策略初始化' % self.name)

        pastbar = self.loadHistoryBar(self.activeSymbol,
                            type_ = "1min", 
                            size = self.initbars)
        pastbar2=self.loadHistoryBar(self.passiveSymbol,type_="1min",size=self.initbars)

        self.count=0
        self.alpha=0
        # self.floors=[5,6,7]
        # self.floor_infoMap={floor:{"pos":0} for floor in self.floors}
        # self.first_floor=list(self.floor_infoMap.keys())[0]
        # self.last_floor=list(self.floor_infoMap.keys())[-1]    
        # self.profit=[5,6,7]
        # self.passive_floorMap={}
        # self.open_closeGap={floor:floor-profit for floor,profit in zip(self.floor_infoMap.keys(),self.profit)}
        self.passiveDateTime=[]
        self.activeDateTime=[]

        # self.base_unit=1
        for bar,bar2 in zip(pastbar,pastbar2):
            self.barSpreadBuffer.append(bar.close-bar2.close)
            self.barBufferDict[self.passiveSymbol].append(bar2.close)
            self.barBufferDict[self.activeSymbol].append(bar.close)
            self.activeDateTime.append(bar.datetime)
            self.passiveDateTime.append(bar2.datetime)
        x=np.array(self.barBufferDict[self.passiveSymbol][-240:])
        y=np.array(self.barBufferDict[self.activeSymbol][-240:])
        self.gap_base=0.001*np.mean(x+y)/2
            # self.alpha=float(np.mean(y)-np.mean(x))
        self.miu=np.mean(self.barSpreadBuffer[-240:])
        # #用240min的分钟bar预估miu和gap
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' % self.name)
        if self.posDict[self.activeSymbol+"_LONG"]==self.posDict[self.passiveSymbol+'_SHORT'] and self.posDict[self.passiveSymbol+'_SHORT']>0 and self.posDict[self.activeSymbol+"_LONG"]>0:
            self.pos=-1
            self.volume=self.posDict[self.passiveSymbol+'_SHORT']
        elif self.posDict[self.activeSymbol+"_SHORT"]==self.posDict[self.passiveSymbol+'_LONG'] and self.posDict[self.passiveSymbol+'_LONG']>0 and self.posDict[self.activeSymbol+"_SHORT"]>0:
            self.pos=1
            self.volume=self.posDict[self.passiveSymbol+'_LONG']
        path = os.path.abspath(os.path.dirname(__file__))
        filename=os.path.join(path,"Ye.json")
        with open(filename) as f:
            info=json.load(f)
            info=info[self.activeSymbol]
            self.rev_floor=info["rev_floor"]
            
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' % self.name)
        self.putEvent()
        

    # ----------------------------------------------------------------------
    
    
    def onTick(self, tick):
        """收到行情TICK推送"""
        self.bgDict[tick.vtSymbol].updateTick(tick)
        self.tickBufferDict[tick.vtSymbol].append(tick)
       
       #保证两边都有数据才开始进行后面的交易
        if not self.tickBufferDict[self.activeSymbol]:
            return 
        if not self.tickBufferDict[self.passiveSymbol]:
            return
        
        if len(self.tickBufferDict[self.activeSymbol])>=20000 and len(self.tickBufferDict[self.passiveSymbol])>=20000:
            del self.tickBufferDict[self.activeSymbol][:-5000]
            del self.tickBufferDict[self.passiveSymbol][:-5000]
        #流动性差的品种的bid1和ask1的均值作为计pread的价格
        midPassive=(self.tickBufferDict[self.passiveSymbol][-1].askPrice1+self.tickBufferDict[self.passiveSymbol][-1].bidPrice1)/2
        #流动性好的品种的bid1和ask1的均值作为计算spread的价格
        midActive=(self.tickBufferDict[self.activeSymbol][-1].askPrice1+self.tickBufferDict[self.activeSymbol][-1].bidPrice1)/2
        #用passive的Buffer存下来midPassive，方便计算均值
        self.midPassiveBuffer.append(midPassive)
        #用active的Buffer存下来midActive，方便计算均值
        self.midActiveBuffer.append(midActive)
        
        #用spread表示价差，但该价差是假定beta=1的时候算-self.alpha出来的，线性回归的sigma（残差）
        spread=midActive-midPassive-self.alpha
        self.spreadBuffer.append(spread)
        
        if len(self.spreadBuffer)==30000:
            del self.spreadBuffer[:-3000]
        
        #买价-卖价
        abpassive = self.tickBufferDict[self.passiveSymbol][-1].askPrice1 - self.tickBufferDict[self.passiveSymbol][-1].bidPrice1
        abactive = self.tickBufferDict[self.activeSymbol][-1].askPrice1 - self.tickBufferDict[self.activeSymbol][-1].bidPrice1
        
        bid_askSpread=self.tickBufferDict[self.activeSymbol][-1].bidPrice1-self.tickBufferDict[self.activeSymbol][-1].askPrice1
        self.cost = 1/2*(abpassive + abactive)+ \
               2*0.0005*(self.tickBufferDict[self.activeSymbol][-1].lastPrice + self.tickBufferDict[self.passiveSymbol][-1].lastPrice)          
        
        self.count+=1
        if self.count==20:
#             self.writeCtaLog("本地撤单")
            for passiveID in self.passive_countList:
                self.cancelOrder(passiveID)
        elif self.count==30:
            self.count=0
        elif self.count==10:


            #如果passive的仓位加上正在挂单的passive的仓位要小于限定的最大仓位

                #第一层

            if self.pos==1 and bid_askSpread<self.gap_base:

                gap_base=self.gap_base

                rev_floor=self.rev_floor

                miu=self.miu
                
                rev_floor=self.rev_floor
                
                volume=self.volume
                closeID=self.sell(self.passiveSymbol,self.tickBufferDict[self.activeSymbol][-1].askPrice1-self.alpha-miu-gap_base*rev_floor,volume,priceType=PRICETYPE_LIMITPRICE,levelRate=10)[0]
                if  closeID:
    
                    self.pos=-3
                    self.passive_countList.append(closeID)
                
                
                    
                    
                    
            elif self.pos==-1 and bid_askSpread<self.gap_base:
                gap_base=self.gap_base

                rev_floor=self.rev_floor

                miu=self.miu
                
                volume=self.volume
                
                closeID=self.cover(self.passiveSymbol,self.tickBufferDict[self.activeSymbol][-1].bidPrice1-self.alpha-miu+gap_base*rev_floor,volume,priceType=PRICETYPE_LIMITPRICE,levelRate=10)[0]
                if  closeID:
                    self.pos=-2
                    self.passive_countList.append(closeID)

        self.putEvent()

    # ----------------------------------------------------------------------
    
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        self.amDict[bar.vtSymbol].updateBar(bar)
        self.writeCtaLog("onBar")
        
        if bar.vtSymbol==self.activeSymbol:
            self.activeDateTime.append(bar.datetime)
            if len(self.passiveDateTime)==0:
                return 
            elif abs((bar.datetime-self.activeDateTime[-1]).total_seconds())<=5:
                self.barBufferDict[self.activeSymbol].append(bar.close)
                if len(self.barBufferDict[self.passiveSymbol])==0:
                    return
                self.barSpreadBuffer.append(bar.close-self.barBufferDict[self.passiveSymbol][-1]-self.alpha)
        elif bar.vtSymbol==self.passiveSymbol:
            self.passiveDateTime.append(bar.datetime)
            if len(self.activeDateTime)==0:
                return 
            elif abs((bar.datetime-self.activeDateTime[-1]).total_seconds())<=5:
                self.barBufferDict[self.passiveSymbol].append(bar.close)

        
        if len(self.barSpreadBuffer)%240==0 and len(self.barBufferDict[self.passiveSymbol])>240 and len(self.barBufferDict[self.activeSymbol])>240:
            x=np.array(self.barBufferDict[self.passiveSymbol][-240:])
            y=np.array(self.barBufferDict[self.activeSymbol][-240:])
            self.gap_base=0.001*np.mean(x+y)/2
            # self.alpha=float(np.mean(y)-np.mean(x))
            self.miu=np.mean(self.barSpreadBuffer[-240:])
        
        if len(self.barSpreadBuffer)%2400==0:
            del self.barBufferDict[self.passiveSymbol][:-240]
            del self.barBufferDict[self.activeSymbol][:-240]
            del self.activeDateTime[:-240]
            del self.passiveDateTime[:-240]
            del self.barSpreadBuffer[:-240]
        
        
        # for floor in self.floors:
        #     pos=self.floor_infoMap[floor]["pos"]
        #     if pos==-1: 
        #         miu=self.floor_infoMap[floor]["miu"]
        #         gap=self.gap_base*floor
        #         volume=self.floor_infoMap[floor]["volume"]
                
        #         if (self.spreadBuffer[-1]<miu-4*gap or self.miu<miu-gap):
        #             closeID=self.cover(self.passiveSymbol,self.midPassiveBuffer[-1]*1.02,volume,marketPrice=0)[0]
        #             self.close_openIdMap[closeID]=self.floor_infoMap[floor]["passiveID"]
        #             self.floor_infoMap[floor]["pos"]=-2
        #             if self.spreadBuffer[-1]<miu-4*gap:
        #                 self.writeCtaLog("向下偏离价差强平")
        #             else:
        #                 self.writeCtaLog("miu向下突破miu-gap")
        #     elif pos==1: 
        #         miu=self.floor_infoMap[floor]["miu"]
        #         gap=self.gap_base*floor
        #         volume=self.floor_infoMap[floor]["volume"]
                
        #         if (self.spreadBuffer[-1]>miu+4*gap or self.miu>miu+gap):
        #             closeID=self.sell(self.passiveSymbol,self.midPassiveBuffer[-1]*0.98,volume,marketPrice=0)[0]
                    
        #             self.close_openIdMap[closeID]=self.floor_infoMap[floor]["passiveID"]
        #             self.floor_infoMap[floor]["pos"]=-3
        #             if self.spreadBuffer[-1]>miu+4*gap:
        #                 self.writeCtaLog("向上偏离价差强平")
        #             else:
        #                 self.writeCtaLog("miu向上突破miu+gap")

            

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""

        
        if order.status=="未成交" and order.vtSymbol==self.passiveSymbol:
            pass
        if order.status=="全部成交" or order.status=="部分成交":
            volume=order.thisTradedVolume
            if order.vtSymbol==self.passiveSymbol:                    
                if order.direction=="多"  and order.offset=="平仓":
#                     print("市价追平多")
                    self.sell(self.activeSymbol,self.midActiveBuffer[-1]*0.98,volume,priceType=PRICETYPE_LIMITPRICE,levelRate=10)[0]
                    
                    # del self.close_openIdMap[order.vtOrderID]
                    self.writeCtaLog("市价追平多"+str(self.midActiveBuffer[-1]))
                    
                elif order.direction=="空" and order.offset=="平仓":
#                     print("市价追平空")
                    self.cover(self.activeSymbol,self.midActiveBuffer[-1]*1.02,volume,priceType=PRICETYPE_LIMITPRICE,levelRate=10)[0]
                    
                    self.writeCtaLog("市价追平空"+str(self.midActiveBuffer[-1]))
                    
                # if activeID:
                    # self.active_passiveMap[activeID]=passiveID

            if order.vtSymbol==self.activeSymbol and order.direction=="平仓":
                self.volume-=volume
                self.writeCtaLog("平仓"+"***"+str(order.vtOrderID)+":"+str(self.miu)+" "+str(self.gap_base))
                    
        elif order.status=="已撤销": #只有passive会撤销所以不判断symbol默认passiveSymbol
            if order.offset=="平仓" :#平仓订单撤销把pos和flag修改，让它恢复原样
                pos=self.long_shortToInt[order.direction]
                self.pos=pos
                self.passive_countList.remove(order.vtOrderID)#不管开仓还是平仓订单的count单独维护，在收到未成交的委托的时候被初始化为0
        ###############################____________________
        if order.status=="全部成交":
            if order.vtSymbol==self.activeSymbol and order.offset=="平仓" :
                # passiveID=self.active_passiveMap[order.vtOrderID]
                self.pos=0
                # del self.active_passiveMap[order.vtOrderID]
            elif order.vtSymbol==self.passiveSymbol and order.vtOrderID in self.passive_countList:#防止restful怼过去进两遍拒单逻辑
                self.passive_countList.remove(order.vtOrderID)
        if order.status=="拒单":
            if order.vtSymbol==self.passiveSymbol:        
                pos=self.pos_Map[self.pos]
                self.pos=pos
            elif order.vtSymbol==self.activeSymbol:
                if order.rejectedInfo=='20018':
                    volume=order.totalVolume
                    if order.direction=="多"  and order.offset=="平仓":
    #                     print("市价追平多")
                        self.cover(self.activeSymbol,self.midActiveBuffer[-1]*0.98,volume,priceType=PRICETYPE_LIMITPRICE,levelRate=10)[0]
                        
                        self.writeCtaLog("市价追平多"+str(self.midActiveBuffer[-1]))
                        
                    elif order.direction=="空" and order.offset=="平仓":
    #                     print("市价追平空")
                        self.sell(self.activeSymbol,self.midActiveBuffer[-1]*1.02,volume,priceType=PRICETYPE_LIMITPRICE,levelRate=10)[0]
                        
                        
                        self.writeCtaLog("市价追平空"+str(self.midActiveBuffer[-1]))
                if order.rejectedInfo=="20007":
                    #如果再发一遍忽略
                    self.writeCtaLog("volume为0被拒单")

                    

        if order.status=="未知":
            content = u'stg_onorder收到的订单状态, statu:%s, id:%s, vtSymbol:%s'%(order.status, order.vtOrderID, order.vtSymbol)
            self.mail('18955993726@163.com',content)   # 邮件模块可以将信息发送给策略师，第一个参数为收件人邮件地址，第二个参数为邮件正文

        self.writeCtaLog("order.status %s order.vtSymbol %s order.vtOrderID %s order.direction %s order.offset %s order.price:%s cost:%s spread:%s "%(order.status,order.vtSymbol,order.vtOrderID,order.offset,order.direction,order.price,self.cost,self.spreadBuffer[-1]))        

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        # self.writeCtaLog('symbol:%s, price:%s, direction:%s, offset:%s, spread:%s,cost:%s'%(trade.vtSymbol,trade.price,trade.direction,trade.offset,self.spreadBuffer[-1], self.cost))
        
        # self.writeCtaLog("active long %s"%self.posDict[self.activelong])
        # self.writeCtaLog("thread*** %s"%len(list(self.passive_infoMap.keys())))
        # self.writeCtaLog("passive long %s"%self.posDict[self.passivelong])
        # self.writeCtaLog("active short %s"%self.posDict[self.activeshort])
        # self.writeCtaLog("passive short %s"%self.posDict[self.passiveshort])
        pass        
    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass
