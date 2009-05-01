"""Module which contains all spells that check something in a nif file."""

# --------------------------------------------------------------------------
# ***** BEGIN LICENSE BLOCK *****
#
# Copyright (c) 2007-2009, NIF File Format Library and Tools.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials provided
#      with the distribution.
#
#    * Neither the name of the NIF File Format Library and Tools
#      project nor the names of its contributors may be used to endorse
#      or promote products derived from this software without specific
#      prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# ***** END LICENSE BLOCK *****
# --------------------------------------------------------------------------

from __future__ import with_statement
from contextlib import closing
from itertools import izip, repeat
import tempfile

from PyFFI.Formats.NIF import NifFormat
import PyFFI.Spells.NIF
import PyFFI.Utils.TriStrip # for check_tristrip

class SpellReadWrite(PyFFI.Spells.NIF.NifSpell):
    """Like the original read-write spell, but with additional file size
    check."""

    SPELLNAME = "check_readwrite"

    def dataentry(self):
        self.toaster.msgblockbegin("writing to temporary file")

        f_tmp = tempfile.TemporaryFile()
        try:
            self.data.write(f_tmp)
            # comparing the files will usually be different because
            # blocks may have been written back in a different order,
            # so cheaply just compare file sizes
            self.toaster.msg("comparing file sizes")
            self.stream.seek(0, 2)
            f_tmp.seek(0, 2)
            if self.stream.tell() != f_tmp.tell():
                self.toaster.msg("original size: %i" % self.stream.tell())
                self.toaster.msg("written size:  %i" % f_tmp.tell())
                f_tmp.seek(0)
                f_debug = open("debug.nif", "wb")
                f_debug.write(f_tmp.read(-1))
                f_debug.close()
                raise StandardError('write check failed: file sizes differ (written file saved as debug.nif for inspection)')
        finally:
            f_tmp.close()
    
        self.toaster.msgblockend()

        # spell is finished: prevent recursing into the tree
        return False

class SpellNodeNamesByFlag(PyFFI.Spells.NIF.NifSpell):
    """This spell goes over all nif files, and at the end, it gives a summary
    of which node names where used with particular flags."""

    SPELLNAME = "check_nodenamesbyflag"

    @classmethod
    def toastentry(cls, toaster):
        toaster.flagdict = {}
        return True

    @classmethod
    def toastexit(cls, toaster):
        for flag, names in toaster.flagdict.iteritems():
            toaster.msg("%s %s" % (flag, names))

    def datainspect(self):
        return self.inspectblocktype(NifFormat.NiNode)

    def branchinspect(self, branch):
        # stick to main tree
        return isinstance(branch, NifFormat.NiAVObject)

    def branchentry(self, branch):
        if isinstance(branch, NifFormat.NiAVObject):
            if not branch.flags in self.toaster.flagdict:
                self.toaster.flagdict[branch.flags] = []
            if not branch.name in self.toaster.flagdict[branch.flags]:
                self.toaster.flagdict[branch.flags].append(branch.name)
            return True
        else:
            return False

class SpellCompareSkinData(PyFFI.Spells.NIF.NifSpell):
    """This spell compares skinning data with a reference nif."""

    SPELLNAME = "check_compareskindata"

    # helper functions (to compare with custom tolerance)

    @staticmethod
    def are_vectors_equal(oldvec, newvec, tolerance=0.01):
        return (max([abs(x-y)
                for (x,y) in izip(oldvec.asList(), newvec.asList())])
                < tolerance)

    @staticmethod
    def are_matrices_equal(oldmat, newmat, tolerance=0.01):
        return (max([max([abs(x-y)
                     for (x,y) in izip(oldrow, newrow)])
                    for (oldrow, newrow) in izip(oldmat.asList(),
                                                 newmat.asList())])
                < tolerance)

    @staticmethod
    def are_floats_equal(oldfloat, newfloat, tolerance=0.01):
        return abs(oldfloat - newfloat) < tolerance

    @classmethod
    def toastentry(cls, toaster):
        """Read reference nif file given as argument."""
        # if no argument given, do not apply spell
        if not toaster.options.get("arg"):
            return False
        # read reference nif
        toaster.refdata = NifFormat.Data()
        with closing(open(toaster.options["arg"], "rb")) as reffile:
            toaster.refdata.read(reffile)
        # find bone data in reference nif
        toaster.refbonedata = []
        for refgeom in toaster.refdata.getGlobalIterator():
            if (isinstance(refgeom, NifFormat.NiGeometry)
                and refgeom.skinInstance and refgeom.skinInstance.data):
                toaster.refbonedata += zip(
                    repeat(refgeom.skinInstance.skeletonRoot),
                    repeat(refgeom.skinInstance.data),
                    refgeom.skinInstance.bones,
                    refgeom.skinInstance.data.boneList)
        # only apply spell if the reference nif has bone data
        return bool(toaster.refbonedata)

    def datainspect(self):
        return self.inspectblocktype(NifFormat.NiSkinData)

    def branchinspect(self, branch):
        # stick to main tree
        return isinstance(branch, NifFormat.NiAVObject)

    def branchentry(self, branch):
        if (isinstance(branch, NifFormat.NiGeometry)
            and branch.skinInstance and branch.skinInstance.data):
            for skelroot, skeldata, bonenode, bonedata in izip(
                repeat(branch.skinInstance.skeletonRoot),
                repeat(branch.skinInstance.data),
                branch.skinInstance.bones,
                branch.skinInstance.data.boneList):
                for refskelroot, refskeldata, refbonenode, refbonedata \
                    in self.toaster.refbonedata:
                    if bonenode.name == refbonenode.name:
                        self.toaster.msgblockbegin("checking bone %s"
                                                   % bonenode.name)

                        # check that skeleton roots are identical
                        if skelroot.name == refskelroot.name:
                            # no extra transform
                            branchtransform_extra = NifFormat.Matrix44()
                            branchtransform_extra.setIdentity()
                        else:
                            self.toaster.msg(
                                "skipping: skeleton roots are not identical")
                            self.toaster.msgblockend()
                            continue

                            # the following is an experimental way of
                            # compensating for different skeleton roots
                            # (disabled by default)

                            # can we find skeleton root of data in reference
                            # data?
                            for refskelroot_branch \
                                in self.toaster.refdata.getGlobalIterator():
                                if not isinstance(refskelroot_branch,
                                                  NifFormat.NiAVObject):
                                    continue
                                if skelroot.name == refskelroot_branch.name:
                                    # yes! found!
                                    #self.toaster.msg(
                                    #    "found alternative in reference nif")
                                    branchtransform_extra = \
                                        refskelroot_branch.getTransform(refskelroot).getInverse()
                                    break
                            else:
                                for skelroot_ref \
                                    in self.data.getGlobalIterator():
                                    if not isinstance(skelroot_ref,
                                                      NifFormat.NiAVObject):
                                        continue
                                    if refskelroot.name == skelroot_ref.name:
                                        # yes! found!
                                        #self.toaster.msg(
                                        #    "found alternative in nif")
                                        branchtransform_extra = \
                                            skelroot_ref.getTransform(skelroot)
                                        break
                                else:
                                    self.toaster.msgblockbegin("""\
skipping: skeleton roots are not identical
          and no alternative found""")
                                    self.toaster.msgblockend()
                                    continue

                        # calculate total transform matrix that would be applied
                        # to a vertex in the reference geometry in the position
                        # of the reference bone
                        reftransform = (
                            refbonedata.getTransform()
                            * refbonenode.getTransform(refskelroot)
                            * refskeldata.getTransform())
                        # calculate total transform matrix that would be applied
                        # to a vertex in this branch in the position of the
                        # reference bone
                        branchtransform = (
                            bonedata.getTransform()
                            * refbonenode.getTransform(refskelroot) # NOT a typo
                            * skeldata.getTransform()
                            * branchtransform_extra) # skelroot differences
                        # compare
                        if not self.are_matrices_equal(reftransform,
                                                       branchtransform):
                            #raise ValueError(
                            self.toaster.msg(
                                "transform mismatch\n%s\n!=\n%s\n"
                                % (reftransform, branchtransform))

                        self.toaster.msgblockend()
            # stop in this branch
            return False
        else:
            # keep iterating
            return True

class SpellCheckBhkBodyCenter(PyFFI.Spells.NIF.NifSpell):
    """Recalculate the center of mass and inertia matrix,
    compare them to the originals, and report accordingly.
    """

    SPELLNAME = "check_bhkbodycenter"

    def datainspect(self):
        return self.inspectblocktype(NifFormat.bhkRigidBody)

    def branchinspect(self, branch):
        return isinstance(branch, (NifFormat.NiAVObject,
                                   NifFormat.bhkNiCollisionObject,
                                   NifFormat.bhkRigidBody))

    def branchentry(self, branch):
        if not isinstance(branch, NifFormat.bhkRigidBody):
            # keep recursing
            return True
        else:
            self.toaster.msg("getting rigid body mass, center, and inertia")
            mass = branch.mass
            center = branch.center.getCopy()
            inertia = branch.inertia.getCopy()

            self.toaster.msg("recalculating...")
            branch.updateMassCenterInertia(mass=branch.mass)

            #self.toaster.msg("checking mass...")
            #if mass != branch.mass:
            #    #raise ValueError("center does not match; original %s, calculated %s"%(center, branch.center))
            #    self.toaster.logger.warn("warning: mass does not match; original %s, calculated %s"%(mass, branch.mass))
            #    # adapt calculated inertia matrix with observed mass
            #    if mass > 0.001:
            #        correction = mass / branch.mass
            #        for i in xrange(12):
            #            branch.inertia[i] *= correction
            #else:
            #    self.toaster.msg("perfect match!")

            self.toaster.msg("checking center...")
            if center != branch.center:
                #raise ValueError("center does not match; original %s, calculated %s"%(center, branch.center))
                self.toaster.logger.warn(
                    "center does not match; original %s, calculated %s"
                    % (center, branch.center))

            self.toaster.msg("checking inertia...")

            scale = max(max(abs(x) for x in row) for row in inertia.asList() + branch.inertia.asList())
            if (max(max(abs(x - y)
                        for x, y in zip(row1, row2))
                    for row1, row2 in zip(inertia.asList(), branch.inertia.asList()))
                > 0.1 * scale):
                #raise ValueError("center does not match; original %s, calculated %s"%(center, branch.center))
                self.toaster.logger.warn(
                    "inertia does not match:\n\noriginal\n%s\n\ncalculated\n%s\n"
                    % (inertia, branch.inertia))
            # stop recursing
            return False

class SpellCheckCenterRadius(PyFFI.Spells.NIF.NifSpell):
    """Recalculate the center and radius, compare them to the originals,
    and report mismatches.
    """
    # tentative results
    # -----------------
    # oblivion: ok
    # civ4: mostly ok (with very few exceptions: effects/magpie/flock.nif, units/!errorunit/bear.nif, maybe some more)
    # daoc: ok
    # morrowind: usually ok (quite some exceptions here)
    # zoo tycoon 2: mostly ok (except *_Adult_*.nif files)

    SPELLNAME = "check_centerradius"

    def datainspect(self):
        return self.inspectblocktype(NifFormat.NiGeometry)

    def branchinspect(self, branch):
        return isinstance(branch, (NifFormat.NiAVObject,
                                   NifFormat.NiGeometry,
                                   NifFormat.NiGeometryData))

    def branchentry(self, branch):
        if not isinstance(branch, NifFormat.NiGeometryData):
            # keep recursing
            return True
        else:
            self.toaster.msg("getting bounding sphere")
            center = NifFormat.Vector3()
            center.x = branch.center.x
            center.y = branch.center.y
            center.z = branch.center.z
            radius = branch.radius

            self.toaster.msg("checking that all vertices are inside")
            maxr = 0.0
            maxv = None
            for vert in branch.vertices:
                dist = vert - center
                if dist * dist > maxr:
                    maxr = dist * dist
                    maxv = vert
            maxr = maxr ** 0.5

            if maxr > 1.01 * radius + 0.01:
                #raise ValueError(
                self.toaster.logger.warn(
                   "not all vertices inside bounding sphere (vertex %s, error %s)"
                   % (maxv, abs(maxr - radius)))

            self.toaster.msg("recalculating bounding sphere")
            branch.updateCenterRadius()

            self.toaster.msg("comparing old and new spheres")
            if center != branch.center:
               self.toaster.logger.warn(
                   "center does not match; original %s, calculated %s"
                   % (center, branch.center))
            if abs(radius - branch.radius) > NifFormat.EPSILON:
               self.toaster.logger.warn(
                   "radius does not match; original %s, calculated %s"
                   % (radius, branch.radius))
            # stop recursing
            return False

class SpellCheckSkinCenterRadius(PyFFI.Spells.NIF.NifSpell):
    """Recalculate the skindata center and radius for each bone, compare them
    to the originals, and report mismatches.
    """

    SPELLNAME = "check_skincenterradius"

    def datainspect(self):
        return self.inspectblocktype(NifFormat.NiSkinData)

    def branchinspect(self, branch):
        return isinstance(branch, (NifFormat.NiAVObject,
                                   NifFormat.NiGeometry))

    def branchentry(self, branch):
        if not(isinstance(branch, NifFormat.NiGeometry) and branch.isSkin()):
            # keep recursing
            return True
        else:
            self.toaster.msg("getting skindata block bounding spheres")
            center = []
            radius = []
            for skindatablock in branch.skinInstance.data.boneList:
                center.append(skindatablock.boundingSphereOffset.getCopy())
                radius.append(skindatablock.boundingSphereRadius)

            self.toaster.msg("recalculating bounding spheres")
            branch.updateSkinCenterRadius()

            self.toaster.msg("comparing old and new spheres")
            for i, skindatablock in enumerate(branch.skinInstance.data.boneList):
                if center[i] != skindatablock.boundingSphereOffset:
                    self.toaster.logger.error(
                        "%s center does not match; original %s, calculated %s"
                        % (branch.skinInstance.bones[i].name,
                           center[i], skindatablock.boundingSphereOffset))
                if abs(radius[i] - skindatablock.boundingSphereRadius) \
                    > NifFormat.EPSILON:
                    self.toaster.logger.error(
                        "%s radius does not match; original %s, calculated %s"
                        % (branch.skinInstance.bones[i].name,
                           radius[i], skindatablock.boundingSphereRadius))
            # stop recursing
            return False

class SpellCheckConvexVerticesShape(PyFFI.Spells.NIF.NifSpell):
    """This test checks whether each vertex is the intersection of at least
    three planes.
    """
    SPELLNAME = "check_convexverticesshape"

    def datainspect(self):
        return self.inspectblocktype(NifFormat.bhkConvexVerticesShape)

    def branchinspect(self, branch):
        return isinstance(branch, (NifFormat.NiAVObject,
                                   NifFormat.bhkNiCollisionObject,
                                   NifFormat.bhkRefObject))

    def branchentry(self, branch):
        if not isinstance(branch, NifFormat.bhkConvexVerticesShape):
            # keep recursing
            return True
        else:
            self.toaster.msg("checking vertices and planes")
            for v4 in branch.vertices:
                v = NifFormat.Vector3()
                v.x = v4.x
                v.y = v4.y
                v.z = v4.z
                num_intersect = 0
                for n4 in branch.normals:
                    n = NifFormat.Vector3()
                    n.x = n4.x
                    n.y = n4.y
                    n.z = n4.z
                    d   = n4.w
                    if abs(v * n + d) < 0.01:
                        num_intersect += 1
                if num_intersect == 0:
                    self.toaster.logger.error(
                        "vertex %s does not intersect with any plane" % v)
                elif num_intersect == 1:
                    self.toaster.logger.warn(
                        "vertex %s only intersects with one plane" % v)
                elif num_intersect == 2:
                    self.toaster.logger.warn(
                        "vertex %s only intersects with two planes" % v)
            # stop recursing
            return False

class SpellCheckMopp(PyFFI.Spells.NIF.NifSpell):
    """Parse and dump mopp trees, and check their validity:

    * do they have correct origin and scale?
    * do they refer to every triangle exactly once?
    * does the parser visit every byte exactly once?

    Mainly useful to check the heuristic parser and for debugging mopp codes.
    """
    SPELLNAME = "check_mopp"

    def datainspect(self):
        return self.inspectblocktype(NifFormat.bhkMoppBvTreeShape)

    def branchinspect(self, branch):
        return isinstance(branch, (NifFormat.NiAVObject,
                                   NifFormat.bhkNiCollisionObject,
                                   NifFormat.bhkRefObject))

    def branchentry(self, branch):
        if not isinstance(branch, NifFormat.bhkMoppBvTreeShape):
            # keep recursing
            return True
        else:
            mopp = [b for b in branch.moppData]
            o = NifFormat.Vector3()
            o.x = branch.origin.x
            o.y = branch.origin.y
            o.z = branch.origin.z
            scale = branch.scale

            self.toaster.msg("recalculating mopp origin and scale")
            branch.updateOriginScale()

            if branch.origin != o:
                self.toaster.logger.warn("origin mismatch")
                self.toaster.logger.warn("(was %s and is now %s)"
                                         % (o, branch.origin))
            if abs(branch.scale - scale) > 0.5:
                self.toaster.logger.warn("scale mismatch")
                self.toaster.logger.warn("(was %s and is now %s)"
                                         % (scale, branch.scale))

            self.toaster.msg("parsing mopp")
            # ids = indices of bytes processed, tris = triangle indices
            ids, tris = branch.parseMopp(verbose=True)

            error = False

            # check triangles
            counts = [tris.count(i) for i in xrange(branch.shape.data.numTriangles)]
            missing = [i for i in xrange(branch.shape.data.numTriangles)
                       if counts[i] != 1]
            if missing:
                self.toaster.logger.error(
                    "some triangles never visited, or visited more than once")
                self.toaster.logger.debug(
                    "triangles index, times visited")
                for i in missing:
                    self.toaster.logger.debug(i, counts[i])
                error = True

            wrong = [i for i in tris if i > branch.shape.data.numTriangles]
            if wrong:
                self.toaster.logger.error("invalid triangle indices")
                self.toaster.logger.debug(wrong)
                error = True

            # check bytes
            counts = [ids.count(i) for i in xrange(branch.moppDataSize)]
            missing = [i for i in xrange(branch.moppDataSize) if counts[i] != 1]
            if missing:
                self.toaster.logger.error(
                    "some bytes never visited, or visited more than once")
                self.toaster.logger.debug(
                    "byte index, times visited, value")
                for i in missing:
                    self.toaster.logger.debug(i, counts[i], "0x%02X" % mopp[i])
                    self.toaster.logger.debug([mopp[k] for k in xrange(i, min(branch.moppDataSize, i + 10))])
                error = True

            #if error:
            #    raise ValueError("mopp parsing failed")

            # stop recursing
            return False

class SpellCheckTangentSpace(PyFFI.Spells.NIF.NifSpell):
    """Check and recalculate the tangent space, compare them to the originals,
    and report accordingly.
    """
    SPELLNAME = 'check_tangentspace'
    PRECISION = 0.3 #: Difference between values worth warning about.

    def datainspect(self):
        return self.inspectblocktype(NifFormat.NiTriBasedGeom)

    def branchinspect(self, branch):
        return isinstance(branch, NifFormat.NiAVObject)

    def branchentry(self, branch):
        if not isinstance(branch, NifFormat.NiTriBasedGeom):
            # keep recursing
            return True
        else:
            # get tangent space
            tangentspace = branch.getTangentSpace()
            if not tangentspace:
                # no tangent space present
                return False
            self.toaster.msg("checking tangent space")
            oldspace = [] # we will store the old tangent space here
            for i, (n, t, b) in enumerate(tangentspace):
                oldspace.append(n.asList() + t.asList() + b.asList())
                if abs(n * n - 1) > NifFormat.EPSILON:
                    self.toaster.logger.warn(
                        'non-unit normal %s (norm %f) at vertex %i'
                        % (n, (n * n) ** 0.5, i))
                if abs(t * t - 1) > NifFormat.EPSILON:
                    self.toaster.logger.warn(
                        'non-unit tangent %s (norm %f) at vertex %i'
                        % (t, (t * t) ** 0.5, i))
                if abs(b * b - 1) > NifFormat.EPSILON:
                    self.toaster.logger.warn(
                        'non-unit binormal %s (norm %f) at vertex %i'
                        % (b, (b * b) ** 0.5, i))
                if abs(n * t) + abs(n * b) > NifFormat.EPSILON:
                    volume = n * t.crossproduct(b)
                    self.toaster.logger.warn(
                        'non-ortogonal tangent space at vertex %i' % i)
                    self.toaster.logger.warn(
                        'n * t = %s * %s = %f'%(n, t, n * t))
                    self.toaster.logger.warn(
                        'n * b = %s * %s = %f'%(n, b, n * b))
                    self.toaster.logger.warn(
                        't * b = %s * %s = %f'%(t, b, t * b))
                    self.toaster.logger.warn(
                        'volume = %f' % volume)
            # recalculate the tangent space
            branch.updateTangentSpace()
            newspace = [] # we will store the old tangent space here
            for i, (n, t, b) in enumerate(branch.getTangentSpace()):
                newspace.append(n.asList() + t.asList() + b.asList())
            # check if old matches new
            for i, (old, new) in enumerate(izip(oldspace, newspace)):
                for oldvalue, newvalue in izip(old, new):
                    # allow fairly big error
                    if abs(oldvalue - newvalue) > self.PRECISION:
                        self.toaster.logger.warn(
                            'calculated tangent space differs from original '
                            'at vertex %i' % i)
                        self.toaster.logger.warn('old: %s' % old[0:3])
                        self.toaster.logger.warn('old: %s' % old[3:6])
                        self.toaster.logger.warn('old: %s' % old[6:9])
                        self.toaster.logger.warn('new: %s' % new[0:3])
                        self.toaster.logger.warn('new: %s' % new[3:6])
                        self.toaster.logger.warn('new: %s' % new[6:9])
                        break
            
            # don't recurse further
            return False 

class SpellCheckTriStrip(PyFFI.Spells.NIF.NifSpell):
    """Run the stripifier on all triangles from nif files. This spell is also
    useful for checking and profiling the stripifierand the
    stitcher/unstitcher  (for instance it checks that it does not
    change the geometry).

    Reports at the end with average strip length (this is useful to compare
    various stripification algorithms over a large collection of geometries).
    """
    SPELLNAME = 'check_tristrip'

    @classmethod
    def toastentry(cls, toaster):
        toaster.striplengths = []
        return True

    @classmethod
    def toastexit(cls, toaster):
        toaster.msg("average strip length = %f"
                    % (sum(toaster.striplengths)
                       / float(len(toaster.striplengths))))

    def datainspect(self):
        return self.inspectblocktype(NifFormat.NiTriBasedGeomData)

    def branchinspect(self, branch):
        return isinstance(branch, (NifFormat.NiAVObject,
                                   NifFormat.NiTriBasedGeomData))

    def branchentry(self, branch):
        if not isinstance(branch, NifFormat.NiTriBasedGeomData):
            # keep recursing
            return True
        else:
            # get triangles
            self.toaster.msg('getting triangles')
            triangles = branch.getTriangles()
            self.toaster.msg('calculating strips')
            try:
                strips = PyFFI.Utils.TriStrip.stripify(
                    triangles, stitchstrips=False)
            except StandardError:
                self.toaster.logger.error('failed to strip triangles')
                self.toaster.logger.error('%s' % triangles)
                raise
            self.toaster.msg('stripified with %i strips' % len(strips))

            # keep track of strip length
            self.toaster.striplengths += [len(strip) for strip in strips]

            self.toaster.msg('checking strip triangles')
            PyFFI.Utils.TriStrip._checkStrips(triangles, strips)

            self.toaster.msg('checking stitched strip triangles')
            stitchedstrip = PyFFI.Utils.TriStrip.stitchStrips(strips)
            PyFFI.Utils.TriStrip._checkStrips(triangles, [stitchedstrip])

            self.toaster.msg('checking unstitched strip triangles')
            unstitchedstrips = PyFFI.Utils.TriStrip.unstitchStrip(stitchedstrip)
            PyFFI.Utils.TriStrip._checkStrips(triangles, unstitchedstrips)

class SpellCheckVersion(PyFFI.Spells.NIF.NifSpell):
    """Checks all versions used by the files (without reading the full files).
    """
    SPELLNAME = 'check_version'

    @classmethod
    def toastentry(cls, toaster):
        toaster.versions = {} # counts number of nifs with version
        toaster.user_versions = {} # tracks used user version's per version
        toaster.user_version2s = {} # tracks used user version2's per version
        return True

    @classmethod
    def toastexit(cls, toaster):
        for version in toaster.versions:
            toaster.msgblockbegin("version 0x%08X" % version)
            toaster.msg("number of nifs: %s" % toaster.versions[version])
            toaster.msg("user version:  %s" % toaster.user_versions[version])
            toaster.msg("user version2: %s" % toaster.user_version2s[version])
            toaster.msgblockend()

    def datainspect(self):
        # some shortcuts
        version = self.data.version
        user_version = self.data.user_version
        user_version2 = self.data.user_version2
        # report
        self.toaster.msg("version      0x%08X" % version)
        self.toaster.msg("user version %i" % user_version)
        self.toaster.msg("user version %i" % user_version2)
        # update stats
        if version not in self.toaster.versions:
            self.toaster.versions[version] = 0
            self.toaster.user_versions[version] = []
            self.toaster.user_version2s[version] = []
        self.toaster.versions[version] += 1
        if user_version not in self.toaster.user_versions[version]:
            self.toaster.user_versions[version].append(user_version)
        if user_version2 not in self.toaster.user_version2s[version]:
            self.toaster.user_version2s[version].append(user_version2)
        return False