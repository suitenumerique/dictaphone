#import <React/RCTBridgeModule.h>

@interface RCT_EXTERN_MODULE(BundlePath, NSObject)

RCT_EXTERN_METHOD(getBundlePath:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)

@end
