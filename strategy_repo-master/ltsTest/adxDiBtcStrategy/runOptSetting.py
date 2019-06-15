from stepwiseOptClass import stepwiseOpt
import numpy as np
import json
import os
from hlBreakDsStrategy514 import hlBreakDsStrategy

STRATEGYCLASS = hlBreakDsStrategy

# 指定引擎设置
ENGINESETTING = {
                "startDate": "20180722 00:00:00",
                "endDate": "20190222 23:59:00",
                "slippage": 0.5,
                "rate": 0.002,
                'setDB_URI': "mongodb://192.168.0.104:27017",
                "dbName": "VnTrader_1Min_Db",
                "symbolList":["btc.usd.q:okef"]
                }


# 优化目标
OPT_TARGET = "sharpeRatio"
# np.arange(0.1,0.2,0.01)
# range(1,10,1)
# 指定优化任务
OPT_TASK = [        
            {"pick_freq_param": 
                {
                "changeVolatilityPeriod": range(20,61,5),
                "erthreshold": np.arange(0.1, 0.23, 0.02)
                }
            }, 
            {"pick_best_param": 
                {
                "erSemaPeriod": range(4,21,2),
                "erLemaPeriod": range(25,51,5)
                }
            }, 
            {"pick_best_param": 
                {
                "addVar": np.arange(0.5, 1.6, 0.5),
                "sign": ["+", "-", "*", '/']
                }
            }, 
            {"pick_best_param": 
                {
                "takeProfitFirstPct": np.arange(0.04, 0.09, 0.005),
                "posTime": range(1,4)
                }
            }, 
]

# multiSymbolList = [
#                     # ['btc.usd.q:okef'],
#                     ['eos.usd.q:okef'],
#                     ['eth.usd.q:okef'],
#                     ['ltc.usd.q:okef']
#                   ]


def main():
    path = os.path.split(os.path.realpath(__file__))[0]
    with open(path+"//CTA_setting.json") as f:
        globalSetting = json.load(f)[0]

    # for s in multiSymbolList:
    #     ENGINESETTING["symbolList"] = s
    globalSetting.update(ENGINESETTING)
    optimizer = stepwiseOpt(STRATEGYCLASS, ENGINESETTING, OPT_TARGET, OPT_TASK, globalSetting, './optResult')
    optimizer.runMemoryParallel()

if __name__ == '__main__':
    main()