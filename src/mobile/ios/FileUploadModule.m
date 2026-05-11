#import <React/RCTBridgeModule.h>
#import <React/RCTEventEmitter.h>

@interface RCT_EXTERN_MODULE(FileUploadModule, RCTEventEmitter)

RCT_EXTERN_METHOD(uploadFile:(NSString *)filePath
        url:(NSString *)url
        contentType:(NSString *)contentType
        uploadId:(NSString *)uploadId
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

@end
