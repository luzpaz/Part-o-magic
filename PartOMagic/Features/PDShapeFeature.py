import FreeCAD as App
if App.GuiUp:
    import FreeCADGui as Gui
import Part

__title__="PDShapeFeature container"
__author__ = "DeepSOIC"
__url__ = ""

print("loading PDShapeFeature")

def transformCopy(shape, extra_placement = None):
    """transformCopy(shape, extra_placement = None): creates a deep copy shape with shape's placement applied to 
    the subelements (the placement of returned shape is zero)."""
    
    if extra_placement is None:
        extra_placement = App.Placement()
    ret = shape.copy()
    if ret.ShapeType == "Vertex":
        # oddly, on Vertex, transformShape behaves strangely. So we'll create a new vertex instead.
        ret = Part.Vertex(extra_placement.multVec(ret.Point))
    else:
        ret.transformShape(extra_placement.multiply(ret.Placement).toMatrix(), True)
        ret.Placement = App.Placement() #reset placement
    return ret
    
def PlacementsFuzzyCompare(plm1, plm2):
    pos_eq = (plm1.Base - plm2.Base).Length < 1e-7   # 1e-7 is OCC's Precision::Confusion
    
    q1 = plm1.Rotation.Q
    q2 = plm2.Rotation.Q
    # rotations are equal if q1 == q2 or q1 == -q2. 
    # Invert one of Q's if their scalar product is negative, before comparison.
    if q1[0]*q2[0] + q1[1]*q2[1] + q1[2]*q2[2] + q1[3]*q2[3] < 0:
        q2 = [-v for v in q2]
    rot_eq = (  abs(q1[0]-q2[0]) + 
                abs(q1[1]-q2[1]) + 
                abs(q1[2]-q2[2]) + 
                abs(q1[3]-q2[3])  ) < 1e-12   # 1e-12 is OCC's Precision::Angular (in radians)
    return pos_eq and rot_eq


def makePDShapeFeature(name):
    '''makePDShapeFeature(name): makes a PDShapeFeature object.'''
    obj = App.ActiveDocument.addObject("PartDesign::FeaturePython",name)
    proxy = PDShapeFeature(obj)
    vp_proxy = ViewProviderPDShapeFeature(obj.ViewObject)
    return obj

class PDShapeFeature:
    "The PDShapeFeature object"
    def __init__(self,obj):
        self.Type = 'PDShapeFeature'
        obj.addExtension('App::OriginGroupExtensionPython', self)
        obj.addProperty('App::PropertyLink','Tip',"PartDesign","Object to use to form the feature")
        obj.addProperty('App::PropertyEnumeration', 'AddSubType', "PartDesign", "Feature kind")
        obj.addProperty('Part::PropertyPartShape', 'AddSubShape', "PartDesign", "Shape that forms the feature") #TODO: expose PartDesign::AddSub, and use it, instead of mimicking it
        obj.AddSubType = ['Additive', 'Subtractive']
        
        obj.Proxy = self
        

    def execute(self,selfobj):
        import Part
        selfobj.AddSubShape = selfobj.Tip.Shape
        base_feature = selfobj.BaseFeature
        result_shape = None
        if selfobj.AddSubType == 'Additive':
            if base_feature is None:
                result_shape = selfobj.AddSubShape.Solids[0]
            else:
                result_shape = base_feature.Shape.fuse(selfobj.AddSubShape).Solids[0]
        elif selfobj.AddSubType == 'Subtractive':
            result_shape = base_feature.Shape.cut(selfobj.AddSubShape).Solids[0]
        else:
            raise ValueError("AddSub Type not implemented: {t}".format(t= selfobj.AddSubType))
        if not PlacementsFuzzyCompare(selfobj.Placement, result_shape.Placement):
            result_shape = transformCopy(result_shape, selfobj.Placement.inverse()) #the goal is that Placement of selfobj doesn't move the result shape, only the shape being fused up
        selfobj.Shape = result_shape
            
    def advanceTip(self, selfobj, new_object):
        print("advanceTip")
        from PartOMagic.Gui.Utils import screen
        old_tip = screen(selfobj.Tip)
        new_tip = old_tip
        if old_tip is None:
            new_tip = new_object
        if old_tip in new_object.OutList:
            new_tip = new_object
        
        if new_tip is None: return
        if new_tip is old_tip: return
        if new_tip.Name.startswith('Clone'): return
        if new_tip.Name.startswith('ShapeBinder'): return
        selfobj.Tip = new_tip
        
class ViewProviderPDShapeFeature:
    "A View Provider for the PDShapeFeature object"

    def __init__(self,vobj):
        vobj.addExtension('Gui::ViewProviderGeoFeatureGroupExtensionPython', self)
        vobj.Proxy = self
        
    def getIcon(self):
        from PartOMagic.Gui.Utils import getIconPath
        return getIconPath('PartOMagic_PDShapeFeature_{Additive}.svg'.format(Additive= self.Object.AddSubType) )

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
    
    def doubleClicked(self, vobj):
        from PartOMagic.Gui.Observer import activeContainer, setActiveContainer
        ac = activeContainer()
        if ac is vobj.Object:
            setActiveContainer(vobj.Object.Document) #deactivate self
        else:
            setActiveContainer(vobj.Object) #activate self
            Gui.Selection.clearSelection()
        return True
    
    def activationChanged(self, vobj, old_active_container, new_active_container, event):
        # event: -1 = leaving (active container was self or another container inside, new container is outside)
        #        +1 = entering (active container was outside, new active container is inside)
        if event == +1:
            self.oldMode = vobj.DisplayMode
            vobj.DisplayMode = 'Group'
        elif event == -1:
            if self.oldMode == 'Group':
                self.oldMode = 'Flat Lines'
            vobj.DisplayMode = self.oldMode
  
    def __getstate__(self):
        return None

    def __setstate__(self,state):
        return None
        
    def onDelete(self, feature, subelements): # subelements is a tuple of strings
        try:
            import PartOMagic.Base.Containers as Containers
            body = Containers.getContainer(feature)
            if not body.isDerivedFrom('PartDesign::Body'): return
            if self.ViewObject.Visibility and feature.BaseFeature:
                feature.BaseFeature.ViewObject.show()
            body.removeObject(feature)
        except Exception as err:
            App.Console.PrintError("Error in onDelete: " + err.message)
        return True


def CreatePDShapeFeature(name, add_sub_type= 'Additive'):
    App.ActiveDocument.openTransaction("Create PDShapeFeature")
    Gui.addModule('PartOMagic.Features.PDShapeFeature')
    Gui.doCommand('body = PartOMagic.Base.Containers.activeContainer()')
    Gui.doCommand('f = PartOMagic.Features.PDShapeFeature.makePDShapeFeature(name = {name})'.format(name= repr(name)))
    Gui.doCommand('PartOMagic.Base.Containers.addObjectTo(body, f)')
    Gui.doCommand('if f.BaseFeature:\n'
                  '    f.BaseFeature.ViewObject.hide()')
    Gui.doCommand('f.AddSubType = {t}'.format(t= repr(add_sub_type)))
    Gui.doCommand('PartOMagic.Base.Containers.setActiveContainer(f)')
    Gui.doCommand('Gui.Selection.clearSelection()')
    App.ActiveDocument.commitTransaction()


# -------------------------- /common stuff --------------------------------------------------

# -------------------------- Gui command --------------------------------------------------

class CommandPDShapeFeature:
    "Command to create PDShapeFeature feature"
    def __init__(self, add_sub_type):
        self.add_sub_type = add_sub_type
        
    def GetResources(self):
        from PartOMagic.Gui.Utils import getIconPath
        if self.add_sub_type == 'Additive':
            return {'Pixmap'  : getIconPath('PartOMagic_PDShapeFeature_Additive.svg'),
                    'MenuText': "PartDesign addive shape".format(additive= self.add_sub_type),
                    'Accel': '',
                    'ToolTip': "New PartDesign additive shape container. This allows to insert non-PartDesign things into PartDesign sequence."}
        elif self.add_sub_type == 'Subtractive':
            return {'Pixmap'  : getIconPath('PartOMagic_PDShapeFeature_Subtractive.svg'),
                    'MenuText': "PartDesign subtractive shape".format(additive= self.add_sub_type),
                    'Accel': '',
                    'ToolTip': "New PartDesign subtractive shape container. This allows to insert non-PartDesign things into PartDesign sequence."}
        
    def Activated(self):
        CreatePDShapeFeature('{Additive}Shape'.format(Additive= self.add_sub_type), self.add_sub_type)
            
    def IsActive(self):
        from PartOMagic.Base.Containers import activeContainer
        ac = activeContainer()
        return (ac is not None 
                and ac.isDerivedFrom("PartDesign::Body")
                and (ac.Tip is not None or self.add_sub_type == 'Additive'))

if App.GuiUp:
    Gui.addCommand('PartOMagic_PDShapeFeature_Additive',  CommandPDShapeFeature('Additive'))
    Gui.addCommand('PartOMagic_PDShapeFeature_Subtractive',  CommandPDShapeFeature('Subtractive'))

# -------------------------- /Gui command --------------------------------------------------

def exportedCommands():
    return ['PartOMagic_PDShapeFeature_Additive', 'PartOMagic_PDShapeFeature_Subtractive']
