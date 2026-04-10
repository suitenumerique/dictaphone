#import <React/RCTBridgeModule.h>

@interface RCT_EXTERN_MODULE(FileUploadModule, NSObject)

RCT_EXTERN_METHOD(uploadFile:(NSString *)filePath
        url:(NSString *)url
        contentType:(NSString *)contentType
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

@end