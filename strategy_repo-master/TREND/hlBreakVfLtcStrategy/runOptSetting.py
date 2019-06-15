from stepwiseOptClass import stepwiseOpt
import numpy as np
import json
import os
from hlBreakStrategy import hlBreakStrategy

STRATEGYCLASS = hlBreakStrategy

# 指定引擎设置
ENGINESETTING = {
                "startDate": "20180701 00:00:00",
                "endDate": "20190501 23:59:00",
                "contract":[{
                            "slippage": 0.01,
                            "rate": 0.0008,
                           }],
                'setDB_URI': "mongodb://192.168.0.104:27017",
                "dbName": "VnTrader_1Min_Db",
                "symbolList":["ltc.usd.q:okef"]
                }


# 优化目标
OPT_TARGET = "sharpeRatio"
# np.arange(0.1,0.2,0.01)
# range(1,10,1)
# 指定优化任务
OPT_TASK = [
            # {"pick_best_param": 
            #     {
            #      "timeframeMap" : 
            #      [
            #       {"envPeriod": "60m", "signalPeriod":"30m", "tradePeriod":"1m", "filterPeriod": "5m", "addPosPeriod":"5m"},
            #       {"envPeriod": "60m", "signalPeriod":"15m", "tradePeriod":"1m","filterPeriod": "5m", "addPosPeriod":"5m"},
            #       {"envPeriod": "60m", "signalPeriod":"5m", "tradePeriod":"1m","filterPeriod": "5m", "addPosPeriod":"5m"},
            #       {"envPeriod": "30m", "signalPeriod":"30m", "tradePeriod":"1m","filterPeriod": "5m", "addPosPeriod":"5m"},
            #       {"envPeriod": "30m", "signalPeriod":"15m", "tradePeriod":"1m","filterPeriod": "5m", "addPosPeriod":"5m"},
            #       {"envPeriod": "30m", "signalPeriod":"5m", "tradePeriod":"1m","filterPeriod": "5m", "addPosPeriod":"5m"}
            #      ]
            #     }
            # }, 
            {"pick_best_param": 
                {
                "adxPeriod": range(5, 51, 5),
                "adxLowThreshold": range(8, 23, 2)
                }
            }, 
            {"pick_best_param": 
                {
                "adxHighThreshold": range(25,51,5),
                "adxMaxPeriod": range(10, 51, 5)
                }
            }, 
            {"pick_freq_param": 
                {
                "hlEntryPeriod": range(200, 491, 10),
                "hlExitPeriod": range(5, 51, 5)
                }
            },
            # {"pick_best_param": 
            #     {
            #     "barCount": range(1, 7, 1),
            #     "volumePeriod": range(5, 41, 5)
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "volumeSpikeTime": np.arange(2.5, 4.6, 0.5),
            #     "priceSpikePct": np.arange(0.005, 0.026, 0.005)
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "adxPeriod": range(6, 31, 2),
            #     "adxLowThreshold": range(8, 21, 2)
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "adxHighThreshold": range(25,51,5),
            #     "adxMaxPeriod": range(10, 51, 5)
            #     }
            # }, 
            # {"pick_freq_param": 
            #     {
            #     "hlEntryPeriod": range(300, 551, 10),
            #     "hlExitPeriod": range(5, 51, 5)
            #     }
            # },
            # {"pick_freq_param": 
            #     {
            #     "volPeriod": range(20, 61, 5),
            #     "lowVolThreshold": np.arange(0.0005, 0.0021, 0.0005)
            #     }
            # }, 
            # {"pick_freq_param": 
            #     {
            #     "changeVolatilityPeriod": range(5,61,5),
            #     "erthreshold": np.arange(0.1, 0.23, 0.02)
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "erSemaPeriod": range(4,21,2),
            #     "erLemaPeriod": range(25,51,5)
            #     }
            # }, 
            # {"pick_freq_param": 
            #     {
            #     "changeVolatilityPeriod": range(5,61,5),
            #     "erthreshold": np.arange(0.1, 0.23, 0.02)
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "erSemaPeriod": range(4,21,2),
            #     "erLemaPeriod": range(25,51,5)
            #     }
            # }, 
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
    optimizer = stepwiseOpt(STRATEGYCLASS, ENGINESETTING, OPT_TARGET, OPT_TASK, globalSetting, '../optResult')
    optimizer.runMemoryParallel()

if __name__ == '__main__':
    main()