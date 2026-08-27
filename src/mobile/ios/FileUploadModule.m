#import <React/RCTBridgeModule.h>
#import <React/RCTEventEmitter.h>

@interface RCT_EXTERN_MODULE(FileUploadModule, RCTEventEmitter)

RCT_EXTERN_METHOD(uploadFile:(NSString *)filePath
        url:(NSString *)url
        contentType:(NSString *)contentType
        acl:(NSString *)acl
        uploadId:(NSString *)uploadId
        wifiOnly:(BOOL)wifiOnly
        notificationStrings:(NSDictionary *)notificationStrings
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(getUploadStatuses:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(resumeUpload:(NSString *)uploadId
        notificationStrings:(NSDictionary *)notificationStrings
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(waitForUpload:(NSString *)uploadId
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(markUploadFinalized:(NSString *)uploadId
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(clearUpload:(NSString *)uploadId
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(setAppActive:(BOOL)active)

RCT_EXTERN_METHOD(requestNotificationPermission:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(shareAudioFile:(NSString *)filePath
        fileName:(NSString *)fileName
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(deleteLocalFile:(NSString *)filePath
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(localFileExists:(NSString *)filePath
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(listDocumentM4AFiles:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(readBundledFileAsBase64:(NSString *)fileName
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

RCT_EXTERN_METHOD(copyExternalFile:(NSString *)sourceUri
        fileName:(NSString *)fileName
        maxSize:(double)maxSize
        resolver:(RCTPromiseResolveBlock)resolver
        rejecter:(RCTPromiseRejectBlock)rejecter)

@end
