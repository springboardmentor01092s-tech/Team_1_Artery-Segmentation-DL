import {releaseViewer} from './niivue-adapter.js';
import {ctReviewNativePoint} from './ct-review-volume.js';

export async function createCtReviewViewer(canvas,packet,onLocation,signal){
  if(!packet||Object.keys(packet).sort().join(',')!=='ct,geometry')throw new Error('CT-only viewer received an unexpected volume or overlay.');
  const {Niivue,NVImage}=await import('@niivue/niivue');
  if(signal.aborted)throw new DOMException('CT viewer cancelled.','AbortError');
  const viewer=new Niivue({dragAndDropEnabled:false,isNearestInterpolation:true,isRadiologicalConvention:false,
    multiplanarShowRender:0,dragMode:0,dragModePrimary:0,isForceMouseClickToVoxelCenters:true,
    crosshairWidth:.25,crosshairWidthUnit:'percent',
    isColorbar:false,showLegend:false,logLevel:'error',isCornerOrientationText:true,showAllOrientationMarkers:true});
  try{
    await viewer.attachToCanvas(canvas,false);
    if(signal.aborted)throw new DOMException('CT viewer cancelled.','AbortError');
    const ct=await NVImage.new(packet.ct,'original_ct.nii');packet.ct=null;
    if(signal.aborted)throw new DOMException('CT viewer cancelled.','AbortError');
    ct.setAffine(packet.geometry.affine);ct.cal_min=-200;ct.cal_max=800;ct.colormap='gray';
    viewer.addVolume(ct);
    if(viewer.volumes.length!==1)throw new Error('CT-only viewer refused unexpected layers.');
    viewer.setSliceType(viewer.sliceTypeMultiplanar);
    viewer.scene.crosshairPos=Array.from(ct.dimsRAS).slice(1,4).map(n=>(Math.floor(n/2)+.5)/n);
    const notify=()=>{
      const fraction=Array.from(viewer.scene.crosshairPos),world=Array.from(viewer.frac2mm(fraction)).slice(0,3);
      onLocation({fraction,world,native:ctReviewNativePoint(world,packet.geometry),dimensions:Array.from(ct.dimsRAS).slice(1,4),spacing:packet.geometry.spacing});
    };
    viewer.onLocationChange=notify;viewer.drawScene();notify();
    if(viewer.gl.getError()!==viewer.gl.NO_ERROR)throw new Error('GPU allocation failed. Use the verified CT download.');
    return viewer;
  }catch(error){releaseViewer(viewer);throw error;}
}
